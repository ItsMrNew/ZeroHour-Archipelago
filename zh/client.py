from .deathlink_options import DEFAULT_SELECTION, resolve as resolve_deathlink, selected_event, menu_labels as deathlink_menu_labels
from .game_options import DEFAULTS, validate_options, goal_reached
from .gameplay import input_enabled
from .notifications import ItemNotifications
import asyncio
import getpass
import json
import logging
from pathlib import Path
from urllib.parse import urlsplit
import uuid
import time
import math

from websockets.asyncio.client import connect
from websockets.exceptions import WebSocketException

from .detector import VictoryDetector
from .dozer import DozerUnlock
from .builders import BuilderUnlock, BUTTON_NAMES, MENUS
from .builder_selection import SelectableBuilders
from .unlock_menu import UnlockMenu
from .abilities import AbilityController
from .mission_data import ABILITY_ITEMS, ABILITY_CONFIG, LEGACY_ABILITY_CONFIG, PATRIOT_ABILITY_CONFIG
from .mission_data import ALL_BUILDER_ITEMS, GENERALS_CONFIG, GENERALS_POINTS_LIMIT
from .inventory import Inventory, InventorySyncRequired
from .effects import PlayerEffects
from .deathlink import FailureDetector, MissionRestart, mission_state, GAME_CLIENT_RVA
from .quickreset import QuickReset
from .missiongate import MissionControl
from .mission_data import MISSION_SETS, with_set_bonuses, selected_sets, earned_set_bonuses, MISSION_EXTRA_CHECKS
from .memory import GameMemory, MemoryReadError
from .mission_data import BY_ID, GAME, LOCATION_IDS, PROTOCOL_VERSION, DOZER_ITEM_NAME, DOZER_ITEM_ID, ITEM_NAMES, BUILDER_ITEMS, CHALLENGE_NAMES, select_missions, EFFECT_CONFIG, CONSUMABLE_CONFIG
from .state import Progress
from .version import VERSION, SUPPORT_TARGET

LOG = logging.getLogger("ZeroHour")


class IncompatibleRoom(ValueError):
    pass


def server_url(address):
    address = address.strip()
    if not address:
        raise ValueError("A server address is required.")
    if "://" not in address:
        hostname = urlsplit("//" + address).hostname or ""
        # Hosted AP rooms use TLS; local test servers generally do not.
        scheme = "wss" if hostname.lower().rstrip(".") == "archipelago.gg" or hostname.lower().rstrip(".").endswith(".archipelago.gg") else "ws"
        address = scheme + "://" + address
    parsed = urlsplit(address)
    if parsed.scheme not in {"ws", "wss"} or not parsed.hostname or parsed.username or parsed.password:
        raise ValueError("Use host:port, ws://host:port, or wss://host:port.")
    # Also validate the port now, so a typo does not produce an endless retry.
    _ = parsed.port
    return address


class ZeroHourClient:
    def __init__(self, server, slot, password=None, state_dir=Path(".state")):
        self.server, self.slot, self.password = server_url(server), slot, password
        self.state_dir = Path(state_dir)
        self.uuid = str(uuid.uuid4())
        self.progress = None
        self.identity = None
        self.seed = None
        self.acknowledged = set()
        self.location_ids = LOCATION_IDS
        self.detector = VictoryDetector()
        self.inventory = Inventory()
        self.notifications = ItemNotifications()
        self.inventory_confirmed = False
        self.dozer_mode = False
        self.builder_mode = False
        self.menu_mode = False
        self.ability_items = set()
        self.game_options = dict(DEFAULTS)
        self.grace_remaining, self.grace_last = 0, None
        self.sell_refund = 'normal_refund'
        self.generals_mode = False
        self.builder_items = BUILDER_ITEMS
        self.effects_mode = False
        self.consumables_mode = False
        self.death_yaml = None
        self.death_grace_seconds = 0
        self.death_tags_sent = None
        self.death_link = False
        self.death_link_mode = 'full_restart'
        self.sets_mode = False
        self.selected_missions = ()
        self.mission_checks, self.set_checks = 1, 5
        self.enabled_sets = {}
        self.failure_detector = FailureDetector()
        self.death_active = None
        self.death_active_at = 0
        self.death_received = None
        self.death_outgoing = None
        self.death_seen = set()
        self.connected = False
        self.changed = asyncio.Event()
        self.stop = asyncio.Event()

    def apply_deathlink_selection(self):
        selection = self.progress.deathlink_selection if self.progress else DEFAULT_SELECTION
        enabled, mode, grace = resolve_deathlink(selection, self.death_yaml or (False, 'full_restart', 0))
        changed = (self.death_link, self.death_link_mode) != (enabled, mode)
        if changed:
            self.death_active = self.death_received = self.death_outgoing = None
            self.failure_detector.reset()
        self.death_link, self.death_link_mode, self.death_grace_seconds = enabled, mode, grace
        # Lowering/disabling grace applies immediately. Raising it does not grant
        # fresh immunity halfway through a mission; the next reset uses it.
        self.grace_remaining = min(self.grace_remaining, grace * 30)
        if not self.grace_remaining:
            self.grace_last = None
        self.changed.set()

    def deathlink_event(self, event):
        if self.progress is None or self.death_yaml is None:
            return
        selected = selected_event(self.progress.deathlink_selection, event)
        if selected == self.progress.deathlink_selection:
            return
        try:
            self.progress.save_deathlink_selection(selected)
        except OSError as error:
            raise MemoryReadError('Could not save DeathLink preference; setting unchanged: ' + str(error)) from error
        self.apply_deathlink_selection()
        LOG.info('DeathLink preference: %s; active: %s; grace: %ds.', selected['mode'],
                 self.death_link_mode if self.death_link else 'off', self.death_grace_seconds)

    def deathlink_labels(self):
        return deathlink_menu_labels(self.progress.deathlink_selection if self.progress else DEFAULT_SELECTION,
                                    self.death_yaml or (False, 'full_restart', 0), self.grace_remaining)

    def notification_event(self, event):
        if self.progress is None:
            return
        settings = self.notifications.selection(event)
        try:
            self.progress.save_notification_settings(settings)
        except OSError as error:
            raise MemoryReadError('Could not save notification settings: ' + str(error)) from error
        self.notifications.configure(settings)

    async def sync_deathlink_tags(self, websocket):
        desired = self.death_link
        if self.death_tags_sent is not desired:
            await self.send(websocket, {'cmd': 'ConnectUpdate', 'tags': ['AP', 'DeathLink'] if desired else ['AP']})
            self.death_tags_sent = desired

    def tick_grace(self, state):
        if not self.grace_remaining:
            return
        current = (state.logic, state.campaign, state.mission, state.frame) if state else None
        if current and self.grace_last and current[:3] == self.grace_last[:3]:
            delta = current[3] - self.grace_last[3]
            if 0 < delta <= 90:
                self.grace_remaining = max(0, self.grace_remaining - delta)
        self.grace_last = current

    def victory(self, location):
        if not self.progress or location not in self.location_ids:
            return  # Ignore excluded missions and play before room authentication.
        if self.sets_mode:
            key = BY_ID[location]['campaign']
            if not self.inventory_confirmed or self.inventory.count(MISSION_SETS[key]['item_id']) == 0:
                return
        if location not in self.progress.completed:
            self.progress.mark(location)  # Disk first, then network.
            self.complete_sets()
            LOG.info("Victory: %s (%d mission checks; %d/%d total)", BY_ID[location]["name"],
                     self.mission_checks, len(self.progress.completed), len(self.location_ids))
            self.changed.set()

    def complete_sets(self):
        if not self.sets_mode or self.progress is None:
            return
        extra = {m['id'] for m in MISSION_EXTRA_CHECKS if m['mission_id'] in self.progress.completed
                 and m['check_number'] <= self.mission_checks} & self.location_ids
        if extra - self.progress.completed:
            self.progress.merge(extra)
            self.changed.set()
        new = earned_set_bonuses(self.selected_missions, self.progress.completed, self.set_checks) - self.progress.completed
        if new:
            self.progress.merge(new)
            for key in {BY_ID[i]['campaign'] for i in new}:
                LOG.info('Set complete: %s. Sending %d additional checks.', MISSION_SETS[key]['label'], self.set_checks)
            self.changed.set()

    async def send(self, websocket, *messages):
        await websocket.send(json.dumps(list(messages)))

    async def handle(self, websocket, packet):
        command = packet.get("cmd")
        if command == "RoomInfo":
            self.seed = packet.get("seed_name")
            if not isinstance(self.seed, str) or not self.seed:
                raise IncompatibleRoom("Server did not supply a seed identity.")
            if self.identity and self.seed != self.identity[0]:
                raise IncompatibleRoom("The room's seed changed. Restart the client for the new seed.")
            await self.send(websocket, {
                "cmd": "Connect", "game": GAME, "name": self.slot, "password": self.password,
                "uuid": self.uuid, "version": {"major": 0, "minor": 6, "build": 7, "class": "Version"},
                "items_handling": 7, "tags": ["AP"], "slot_data": True,
            })
        elif command == "ConnectionRefused":
            raise IncompatibleRoom("Connection refused: " + ", ".join(packet.get("errors", [])))
        elif command == "Connected":
            data = packet.get("slot_data", {})
            protocol = data.get("protocol_version")
            expected_goal = "all_selected_missions" if protocol in (4, 5, 6, 7, 8, 9, 10, 11, 12, 13, 14, 15, 16, 17) else "all_campaign_missions"
            if protocol not in (1, 2, 3, 4, 5, 6, 7, 8, 9, 10, 11, 12, 13, 14, 15, 16, PROTOCOL_VERSION) or data.get("goal") != expected_goal:
                raise IncompatibleRoom("This slot needs a compatible Zero Hour world package.")
            if protocol == 2 and data.get("unit_unlocks") != [DOZER_ITEM_NAME]:
                raise IncompatibleRoom("This client supports only the USA Dozer test unlock.")
            if protocol in (3, 4, 5, 6, 7, 8, 9) and (data.get("unit_unlocks") != list(BUILDER_ITEMS.values())
                                  or data.get("builder_scope") != "all_stock_campaign_command_centers"):
                raise IncompatibleRoom("This client requires the stock campaign builder unlock configuration.")
            if protocol in (10, 11, 12, 13, 14, 15, 16, 17):
                if (type(data.get('general_builder_unlocks')) is not bool or data.get('builder_menu') is not True
                        or data.get('builder_scope') != 'campaign_and_challenge_command_centers'):
                    raise IncompatibleRoom('Unsupported Archipelago builder menu configuration.')
                expected_builders = ALL_BUILDER_ITEMS if data['general_builder_unlocks'] else BUILDER_ITEMS
                if data.get('unit_unlocks') != list(expected_builders.values()):
                    raise IncompatibleRoom('Unsupported builder unlock list.')
            else:
                expected_builders = BUILDER_ITEMS
            if self.identity and (self.menu_mode != (protocol in (10, 11, 12, 13, 14, 15, 16, 17)) or self.builder_items != expected_builders):
                raise IncompatibleRoom('Builder configuration changed. Restart this client.')
            if protocol in (5, 6, 7, 8, 9, 10, 11, 12, 13, 14, 15, 16, 17) and data.get("effects") != EFFECT_CONFIG:
                raise IncompatibleRoom("Unsupported cash/power effect configuration.")
            if protocol in (9, 10, 11, 12, 13, 14, 15, 16, 17) and data.get("consumables") != CONSUMABLE_CONFIG:
                raise IncompatibleRoom("Unsupported consumable item configuration.")
            if protocol in (6, 7, 8, 9, 10, 11, 12, 13, 14, 15, 16, 17) and type(data.get('death_link')) is not bool:
                raise IncompatibleRoom('Missing or invalid DeathLink option.')
            if protocol in (7, 8, 9, 10, 11, 12, 13, 14, 15, 16, 17) and data.get('death_link_mode') not in ('full_restart', 'quick_reset'):
                raise IncompatibleRoom('Missing or invalid DeathLink restart mode.')
            if protocol in (12, 13, 14, 15, 16, 17) and data.get('sell_random_building') is not True:
                raise IncompatibleRoom('Unsupported Sell Random Building configuration.')
            sell_refund = data.get('sell_building_refund') if protocol >= 13 else 'normal_refund'
            if sell_refund not in ('normal_refund', 'no_refund') or (self.identity and self.sell_refund != sell_refund):
                raise IncompatibleRoom('Invalid or changed building sale refund mode. Restart this client.')
            generals_mode = data.get('progressive_generals_powers') if protocol >= 14 else False
            if protocol >= 14 and (type(generals_mode) is not bool
                    or data.get('generals_points') != GENERALS_CONFIG
                    or type(data.get('generals_point_items')) is not int
                    or not 0 <= data['generals_point_items'] <= GENERALS_POINTS_LIMIT):
                raise IncompatibleRoom('Unsupported Progressive Generals Powers configuration.')
            if self.identity and self.generals_mode != generals_mode:
                raise IncompatibleRoom('Progressive Generals Powers changed. Restart this client.')
            self.generals_mode = generals_mode
            self.sell_refund = sell_refund
            ability_names = data.get('ability_unlocks', []) if protocol in (11, 12, 13, 14, 15, 16, 17) else []
            if protocol in (11, 12, 13, 14, 15, 16, 17) and (data.get('abilities') != (ABILITY_CONFIG if protocol >= 17 else PATRIOT_ABILITY_CONFIG if protocol >= 13 else LEGACY_ABILITY_CONFIG)
                    or not isinstance(ability_names, list) or any(name not in ABILITY_ITEMS.values() for name in ability_names)
                    or (protocol < 13 and 'Patriot Airdrop' in ability_names)
                    or (protocol < 17 and 'Emergency Repair' in ability_names)
                    or len(set(ability_names)) != len(ability_names)):
                raise IncompatibleRoom('Unsupported ability configuration.')
            ability_items = {item for item, name in ABILITY_ITEMS.items() if name in ability_names}
            if self.identity and self.ability_items != ability_items:
                raise IncompatibleRoom('Ability configuration changed. Restart this client.')
            self.ability_items = ability_items
            mission_checks = data.get('mission_completion_checks') if protocol >= 15 else 1
            set_checks = data.get('set_completion_checks') if protocol >= 8 else 0
            if (type(mission_checks) is not int or not 1 <= mission_checks <= 10
                    or type(set_checks) is not int or not 0 <= set_checks <= 10
                    or (8 <= protocol < 15 and set_checks != 5)):
                raise IncompatibleRoom('Invalid mission/set check counts.')
            if self.identity and (self.mission_checks, self.set_checks) != (mission_checks, set_checks):
                raise IncompatibleRoom('Mission/set check counts changed. Restart this client.')
            expected_locations = LOCATION_IDS
            missions = ()
            if protocol in (4, 5, 6, 7, 8, 9, 10, 11, 12, 13, 14, 15, 16, 17):
                try:
                    missions = select_missions(data["enabled_campaigns"], data["disable_unit_only_missions"], data["selected_challenges"])
                    expected_locations = frozenset(m['id'] for m in (with_set_bonuses(missions, mission_checks, set_checks) if protocol in (8, 9, 10, 11, 12, 13, 14, 15, 16, 17) else missions))
                except (KeyError, TypeError, ValueError) as error:
                    raise IncompatibleRoom("Invalid selected campaign configuration.") from error
            if protocol in (8, 9, 10, 11, 12, 13, 14, 15, 16, 17):
                unlocks = {key: MISSION_SETS[key]['item_id'] for key in selected_sets(missions)}
                starting = data.get('starting_sets')
                if (data.get('mission_set_unlocks') != unlocks
                        or not isinstance(starting, list) or not starting
                        or any(not isinstance(k, str) or k not in unlocks for k in starting)
                        or len(set(starting)) != len(starting)):
                    raise IncompatibleRoom('Invalid mission set unlock/bonus configuration.')
            if set(data.get("location_ids", [])) != expected_locations:
                raise IncompatibleRoom("The slot's mission list does not match its campaign selection.")
            if self.identity and self.location_ids != expected_locations:
                raise IncompatibleRoom("The room's mission selection changed. Restart the client.")
            checked = set(packet.get("checked_locations", []))
            missing = set(packet.get("missing_locations", []))
            if checked | missing != expected_locations or checked & missing:
                raise IncompatibleRoom("The server does not contain the selected mission checks.")
            identity = (self.seed, packet["team"], packet["slot"])
            if self.identity and identity != self.identity:
                raise IncompatibleRoom("The slot identity changed. Restart the client before continuing.")
            try:
                options = validate_options(data.get('game_options'), missions) if protocol >= 16 else dict(DEFAULTS)
            except ValueError as error:
                raise IncompatibleRoom(str(error)) from error
            if self.identity and self.game_options != options:
                raise IncompatibleRoom('Gameplay settings changed. Restart this client.')
            self.game_options = options
            self.location_ids = expected_locations
            if not self.progress:
                self.progress = Progress(self.state_dir, *identity, location_ids=self.location_ids)
                self.inventory = Inventory(self.progress.received)
                self.detector.reset()
            self.identity = identity
            games = self.notifications.connected(packet, self.progress.notification_settings)
            if games:
                await self.send(websocket, {'cmd': 'GetDataPackage', 'games': games})
            self.sets_mode = protocol in (8, 9, 10, 11, 12, 13, 14, 15, 16, 17)
            self.selected_missions = missions
            self.mission_checks, self.set_checks = mission_checks, set_checks
            self.enabled_sets = data['mission_set_unlocks'] if self.sets_mode else {}
            self.dozer_mode = protocol == 2
            self.menu_mode = protocol in (10, 11, 12, 13, 14, 15, 16, 17)
            self.builder_items = expected_builders
            self.builder_mode = protocol in (3, 4, 5, 6, 7, 8, 9, 10, 11, 12, 13, 14, 15, 16, 17)
            self.effects_mode = protocol in (5, 6, 7, 8, 9, 10, 11, 12, 13, 14, 15, 16, 17)
            self.consumables_mode = protocol in (9, 10, 11, 12, 13, 14, 15, 16, 17)
            mode = data['death_link_mode'] if protocol in (7, 8, 9, 10, 11, 12, 13, 14, 15, 16, 17) else 'full_restart'
            yaml_settings = (protocol >= 6 and data['death_link'], mode, self.game_options['death_link_grace_seconds'])
            if self.death_yaml is not None and yaml_settings[1:] != self.death_yaml[1:]:
                raise IncompatibleRoom('DeathLink YAML settings changed. Restart the client for this room.')
            self.death_yaml = yaml_settings
            self.apply_deathlink_selection()
            self.death_tags_sent = None
            self.death_active = self.death_received = self.death_outgoing = None
            self.failure_detector.reset()
            self.acknowledged = checked & self.location_ids
            self.progress.merge(self.acknowledged)
            self.complete_sets()
            self.connected = True
            LOG.info("Connected as %s. %d/%d checks confirmed by server.", self.slot, len(self.acknowledged), len(self.location_ids))
            if protocol in (4, 5, 6, 7, 8, 9, 10, 11, 12, 13, 14, 15, 16, 17):
                LOG.info("Story campaigns: %s. Unit-only missions excluded: %s.",
                         ", ".join(data["enabled_campaigns"]) or "none", data["disable_unit_only_missions"])
                LOG.info("Selected Generals Challenge campaigns: %s.",
                         ", ".join(CHALLENGE_NAMES[c] for c in data["selected_challenges"]) or "none")
            if self.sets_mode:
                LOG.info('Checks: %d per mission; %d additional per completed set.', self.mission_checks, self.set_checks)
            if protocol >= 16:
                goal = self.game_options['victory_goal']
                detail = (MISSION_SETS[self.game_options['goal_final_set']]['label'] + ' final mission' if goal == 'final_mission' else str(self.game_options['goal_set_count']) + ' completed sets' if goal == 'set_count' else 'all enabled mission sets')
                LOG.info('Victory goal: %s. DeathLink grace: %ds; ability cooldowns: %d%%.', detail, self.game_options['death_link_grace_seconds'], self.game_options['ability_cooldown_percent'])
            if self.generals_mode:
                LOG.info('Progressive Generals Powers enabled: received items set points and rank; combat XP does not grant points.')
            if self.builder_mode:
                LOG.info("Cross-faction builders enabled. Waiting for inventory synchronization.")
            if self.menu_mode:
                LOG.info('Archipelago menu enabled: use the top-left button after the opening. Select one unlocked builder per faction, then reselect your Command Center.')
            if self.sets_mode:
                LOG.info('Mission sets locked until their unlock items arrive. Starting sets: %s.',
                         ', '.join(MISSION_SETS[k]['label'] for k in data['starting_sets']))
            if self.dozer_mode:
                LOG.info("USA Dozer test enabled for USA Mission 1. Waiting for inventory synchronization.")
            await self.sync_deathlink_tags(websocket)
            LOG.info('DeathLink: %s.', 'enabled; mission failures send links and received links restart active missions' if self.death_link else 'disabled')
            if self.death_link:
                LOG.info('DeathLink mode: %s.', 'Option 2: Quick Reset (experimental; opening plays once, then checkpoint restores)' if self.death_link_mode == 'quick_reset' else 'Option 1: Full Restart (opening intro replays)')
            self.changed.set()
        elif command == 'Bounced' and self.connected and self.death_link:
            data = packet.get('data', {})
            if 'DeathLink' not in packet.get('tags', []) or not isinstance(data, dict):
                return
            stamp, source = data.get('time'), data.get('source')
            if (type(stamp) not in (int, float) or not math.isfinite(stamp)
                    or not isinstance(source, str) or not source):
                return
            key = (stamp, source)
            if source == self.slot or key in self.death_seen:
                return
            if len(self.death_seen) >= 512:
                # Only recent links can be relevant; prevent an unbounded cache.
                self.death_seen = set(sorted(self.death_seen)[-256:])
            self.death_seen.add(key)
            if self.grace_remaining:
                LOG.info('DeathLink ignored: %d seconds of post-reset grace remain.', math.ceil(self.grace_remaining / 30))
                return
            state = self.death_active
            if state is None or time.monotonic() - self.death_active_at > 1:
                LOG.info('DeathLink from %s ignored: no active mission.', source)
                return
            if self.death_received is None:
                self.death_received = state
                LOG.info('DeathLink received from %s: restarting the current mission.', source)
        elif command == "ReceivedItems":
            if not self.connected or self.progress is None:
                raise IncompatibleRoom("Server sent items before slot authentication.")
            try:
                received = self.inventory.apply(packet.get("index"), packet.get("items"))
            except InventorySyncRequired:
                self.inventory_confirmed = False
                LOG.warning("Item stream interrupted; requesting the full inventory.")
                await self.send(websocket, {"cmd": "Sync"},
                                {"cmd": "LocationChecks", "locations": sorted(self.progress.completed)})
                return
            except ValueError as error:
                raise IncompatibleRoom(f"Invalid item data: {error}") from error
            self.progress.record_inventory(received)
            self.inventory_confirmed = True
            # ReceivedItems is the authoritative inventory, not a second live
            # transfer announcement. PrintJSON logs both incoming and outgoing
            # transfers once, with sender/recipient names and item colours.
            if packet.get("index") == 0:
                LOG.info("Inventory synchronized: %d received items.", len(received))
        elif command == "RoomUpdate" and self.connected:
            self.notifications.update_players(packet.get('players', []))
            checked = set(packet.get("checked_locations", [])) & self.location_ids
            if not checked <= self.acknowledged:
                self.acknowledged |= checked
                self.progress.merge(checked)
                self.complete_sets()
                LOG.info("Server confirmed %d/%d mission checks.", len(self.acknowledged), len(self.location_ids))
                self.changed.set()
        elif command == "DataPackage":
            self.notifications.data_package(packet)
        elif command == "PrintJSON":
            # Both structured transfers and the server /send text notice are
            # live events; the inventory stream replays on reconnect.
            if self.connected:
                event = self.notifications.receive(packet)
                if event is not None:
                    parts = self.notifications.log_parts(event)
                    LOG.info('%s', ''.join(text for text, _ in parts), extra={'item_parts': parts})
                    return
            if packet.get("type") == 'ItemSend':
                return
            def render(part):
                value = str(part.get("text", ""))
                if part.get("type") == "player_id" and self.identity and value == str(self.identity[2]):
                    return self.slot
                if part.get("type") == "item_id" and value.isdigit() and int(value) in ITEM_NAMES:
                    return ITEM_NAMES[int(value)]
                if part.get("type") == "location_id" and value.isdigit() and int(value) in BY_ID:
                    return BY_ID[int(value)]["name"]
                return value
            message = "".join(render(part) for part in packet.get("data", []))
            if message:
                LOG.info("%s", message)
        elif command in {"InvalidPacket", "InvalidArguments"}:
            raise IncompatibleRoom(f"Server rejected a client packet: {packet}")

    async def flush(self, websocket):
        goal_sent = False
        while True:
            try:
                await asyncio.wait_for(self.changed.wait(), timeout=5)
            except asyncio.TimeoutError:
                pass
            self.changed.clear()
            if not self.connected:
                continue
            await self.sync_deathlink_tags(websocket)
            if self.death_link and self.death_outgoing:
                data, self.death_outgoing = self.death_outgoing, None
                self.death_seen.add((data['time'], data['source']))
                await self.send(websocket, {'cmd': 'Bounce', 'tags': ['DeathLink'], 'data': data})
                LOG.info('DeathLink sent: %s', data['cause'])
            pending = self.progress.completed - self.acknowledged
            if pending:
                await self.send(websocket, {"cmd": "LocationChecks", "locations": sorted(pending)})
            # Wait for the server acknowledgement before declaring completion.
            if (goal_reached(self.game_options, self.selected_missions, self.acknowledged) if self.selected_missions else self.acknowledged == self.location_ids) and not goal_sent:
                await self.send(websocket, {"cmd": "StatusUpdate", "status": 30})
                LOG.info("Victory goal complete. %d/%d checks confirmed; remaining checks are still available.", len(self.acknowledged), len(self.location_ids))
                goal_sent = True

    async def receive(self, websocket):
        async for message in websocket:
            packets = json.loads(message)
            if not isinstance(packets, list):
                raise IncompatibleRoom("Invalid server packet format.")
            for packet in packets:
                await self.handle(websocket, packet)

    async def network(self):
        while not self.stop.is_set():
            self.connected = False
            self.inventory.synchronized = False
            try:
                async with connect(self.server, open_timeout=15, max_size=16 * 1024 * 1024) as websocket:
                    LOG.info("Contacting Archipelago server at %s...", self.server)
                    receiving = asyncio.create_task(self.receive(websocket))
                    sending = asyncio.create_task(self.flush(websocket))
                    try:
                        done, _ = await asyncio.wait((receiving, sending), return_when=asyncio.FIRST_COMPLETED)
                        for task in done:
                            task.result()
                    finally:
                        for task in (receiving, sending):
                            task.cancel()
                        await asyncio.gather(receiving, sending, return_exceptions=True)
            except (IncompatibleRoom, json.JSONDecodeError):
                raise
            except (OSError, TimeoutError, WebSocketException) as error:
                from websockets.exceptions import InvalidMessage
                if isinstance(error, InvalidMessage) and self.server.startswith("ws://"):
                    LOG.warning("Server did not accept an unencrypted connection. If this is a hosted room, use wss://host:port.")
                if self.progress is None:
                    LOG.warning("Not connected (%s). Retrying in 5 seconds. Mission tracking starts after login.", error)
                else:
                    LOG.warning("Connection lost (%s). Retrying in 5 seconds; recorded checks remain saved.", error)
            finally:
                self.connected = False
                self.death_active = self.death_received = self.death_outgoing = None
                self.failure_detector.reset()
            await asyncio.sleep(5)

    async def watch(self):
        game = None
        dozer = None
        last_dozer_status = None
        last_status = None
        effects = None
        restart = None
        last_death_status = None
        last_effect_status = None
        menu = None
        last_menu_status = None
        try:
            while True:
                try:
                    if not game:
                        game = GameMemory.find()
                        if not game:
                            status = "Waiting for the Steam Zero Hour game."
                            if status != last_status:
                                LOG.info(status)
                                last_status = status
                            await asyncio.sleep(2)
                            continue
                        LOG.info("Validated Zero Hour engine (PID %d). Support target: %s.", game.pid, SUPPORT_TARGET)
                        # A separate definition gives only ability Patriots zero
                        # energy use, including in saves without a running client.
                        from .ability_assets import ensure_ability_assets
                        try:
                            if ensure_ability_assets(game.path.parent):
                                LOG.info('Installed self-powered Patriot ability assets. Restart Zero Hour once '
                                         'to load them; other client features remain available.')
                        except MemoryReadError as error:
                            LOG.warning('%s', error)
                        self.detector.reset()
                        last_status = None
                    snapshot = game.snapshot()
                    if restart:
                        for message in restart.poll():
                            locked = (isinstance(restart, MissionControl)
                                      and restart.action in (3, 4) and restart.lock_reason is not None)
                            LOG.info('%s', message, extra={'log_colour': '#FA8072' if locked else None})
                        if isinstance(restart, QuickReset) and restart.restored:
                            restart.restored = False
                            # The native load already reconciled saved cash. Do
                            # not treat this load as a second fresh-start bonus.
                            if effects:
                                effects.loading = effects.save_load = effects.start_pending = False
                            self.failure_detector.reset()
                            self.detector.reset()
                    if self.sets_mode and self.progress is not None:
                        if restart is None:
                            restart = MissionControl(game)
                        blocked = not self.inventory_confirmed
                        if self.inventory_confirmed:
                            lock_state = mission_state(game)
                            key = BY_ID[lock_state.location]['campaign'] if lock_state else None
                            reason = None
                            if key is not None:
                                if key not in self.enabled_sets:
                                    reason = f'{MISSION_SETS[key]["label"]} is not enabled in this seed.'
                                elif self.inventory.count(MISSION_SETS[key]['item_id']) == 0:
                                    reason = f'Mission locked: receive {MISSION_SETS[key]["item_name"]}.'
                            blocked = restart.enforce(lock_state, reason) if not (lock_state and lock_state.failed) else bool(reason)
                        if blocked:
                            if menu:
                                menu.suspend()
                            self.detector.reset()
                            self.failure_detector.reset()
                            self.death_active = self.death_received = None
                            await asyncio.sleep(0.1)
                            continue
                    if snapshot is not None and self.progress is not None:
                        location = self.detector.observe(snapshot)
                        if location is not None:
                            self.victory(location)
                    if self.death_link and self.connected:
                        try:
                            state = mission_state(game)
                            incoming, self.death_received = self.death_received, None
                            if incoming:
                                if (state and not state.failed and state.frame >= incoming.frame
                                        and (state.logic, state.campaign, state.mission) == (incoming.logic, incoming.campaign, incoming.mission)):
                                    if restart is None:
                                        restart = QuickReset(game) if self.death_link_mode == 'quick_reset' else MissionRestart(game)
                                    if isinstance(restart, QuickReset) and self.death_link_mode == 'full_restart':
                                        requested = restart._queue(state, 0)
                                    else:
                                        requested = (restart.request(state, self.inventory, self.progress)
                                                     if isinstance(restart, QuickReset) else restart.request(state))
                                    if requested:
                                        self.grace_remaining = self.death_grace_seconds * 30
                                        self.grace_last = None
                                        if menu:
                                            menu.suspend()
                                        if effects:
                                            effects.clear_transient()
                                        self.failure_detector.suppress(state)
                                        self.detector.reset()
                                else:
                                    LOG.info('DeathLink: restart ignored because the mission changed or ended.')
                            playable = state and not state.failed and not (restart and restart.busy) and input_enabled(game)
                            self.tick_grace(state if playable else None)
                            failed = self.failure_detector.observe(state)
                            self.death_active = state if state and not state.failed and not (restart and restart.busy) else None
                            self.death_active_at = time.monotonic()
                            if failed:
                                self.death_outgoing = {'time': time.time(), 'source': self.slot,
                                    'cause': f'{self.slot} failed {BY_ID[failed]["name"].removesuffix(" - Victory")}.'}
                                self.changed.set()
                            last_death_status = None
                        except MemoryReadError as error:
                            self.death_active = None
                            if str(error) != last_death_status:
                                LOG.warning('DeathLink paused: %s', error)
                                last_death_status = str(error)
                    if self.menu_mode and self.progress:
                        if menu is None:
                            if effects is None:
                                effects = PlayerEffects(game, self.progress, expanded=self.consumables_mode, sell_refund=self.sell_refund, generals=self.generals_mode, options=self.game_options)
                            abilities = AbilityController(effects, self.ability_items) if self.ability_items else None
                            menu = UnlockMenu(game, self.progress, self.builder_items, abilities,
                                tracker=(self.selected_missions, self.location_ids), deathlink=self)
                        try:
                            menu.update(self.inventory, settings_only=bool(restart and restart.busy))
                            last_menu_status = None
                        except MemoryReadError as error:
                            if str(error) != last_menu_status:
                                LOG.warning('Archipelago menu paused: %s', error)
                                last_menu_status = str(error)
                    if (self.dozer_mode or self.builder_mode) and self.inventory_confirmed:
                        if restart and restart.busy:
                            await asyncio.sleep(0.1)
                            continue
                        if dozer is None:
                            dozer = SelectableBuilders(game) if self.menu_mode else BuilderUnlock(game) if self.builder_mode else DozerUnlock(game)
                        try:
                            owned = {item for item in self.builder_items if self.inventory.count(item) > 0}
                            status = (dozer.apply_selection(owned, self.progress.builder_choices) if self.menu_mode else
                                      dozer.apply(owned if self.builder_mode else DOZER_ITEM_ID in owned))
                        except MemoryReadError as error:
                            # An experimental unlock failure must not disarm
                            # the working mission victory detector.
                            status = f"Builder update paused: {error}"
                        if status != last_dozer_status:
                            LOG.info("%s", status)
                            last_dozer_status = status
                    if self.effects_mode and self.inventory_confirmed:
                        if effects is None:
                            effects = PlayerEffects(game, self.progress, expanded=self.consumables_mode, sell_refund=self.sell_refund, generals=self.generals_mode, options=self.game_options)
                        try:
                            for message in effects.apply(self.inventory):
                                LOG.info("%s", message)
                            last_effect_status = None
                        except MemoryReadError as error:
                            if str(error) != last_effect_status:
                                LOG.warning("Item effect paused: %s", error)
                                last_effect_status = str(error)
                    if ((self.menu_mode or (self.death_link and self.death_link_mode == 'quick_reset'))
                            and self.connected and self.inventory_confirmed):
                        if restart is None:
                            restart = QuickReset(game)
                        try:
                            ready = (effects is not None and last_effect_status is None
                                     and not effects.start_pending and not effects.cash_waiting
                                     and not (effects.power and effects.power.busy))
                            restart.observe(self.inventory, self.progress, ready,
                                capture_enabled=self.death_link and self.death_link_mode == 'quick_reset')
                        except MemoryReadError as error:
                            if str(error) != last_death_status:
                                LOG.warning('Quick Reset paused: %s', error)
                                last_death_status = str(error)
                except MemoryReadError as error:
                    if str(error) != last_status:
                        LOG.warning("%s", error)
                        last_status = str(error)
                    if game:
                        if restart:
                            try:
                                restart.close()
                            except MemoryReadError:
                                LOG.warning('Could not detach DeathLink hook; restart Zero Hour before another client.')
                            restart = None
                        if menu:
                            try:
                                menu.close()
                            except MemoryReadError:
                                LOG.warning('Could not detach Archipelago menu; restart Zero Hour.')
                            menu = None
                        if effects:
                            try:
                                effects.close()
                            except MemoryReadError:
                                LOG.warning("Could not detach power update hook; restart the game before running another client.")
                        if dozer:
                            try:
                                dozer.restore()
                            except MemoryReadError:
                                LOG.warning("Could not restore builder menus during transition; restart the game if needed.")
                            dozer = None
                        game.close()
                        game = None
                        effects = None
                    self.detector.reset()
                    self.failure_detector.reset()
                    self.death_active = None
                    await asyncio.sleep(2)
                await asyncio.sleep(0.1)
        finally:
            if game:
                if restart:
                    try:
                        restart.close()
                    except MemoryReadError:
                        LOG.warning('Could not detach DeathLink hook; restart Zero Hour before another client.')
                if menu:
                    try:
                        menu.close()
                    except MemoryReadError:
                        LOG.warning('Could not detach Archipelago menu; restart Zero Hour.')
                if effects:
                    try:
                        effects.close()
                    except MemoryReadError:
                        LOG.warning("Could not detach power update hook; restart the game before running another client.")
                if dozer:
                    try:
                        dozer.restore()
                    except MemoryReadError:
                        LOG.warning("Could not restore builder menus; restart the game to restore normal menus.")
                game.close()

    async def run(self):
        tasks = [asyncio.create_task(self.network()), asyncio.create_task(self.watch())]
        try:
            done, _ = await asyncio.wait(tasks, return_when=asyncio.FIRST_COMPLETED)
            for task in done:
                task.result()
        finally:
            for task in tasks:
                task.cancel()
            await asyncio.gather(*tasks, return_exceptions=True)


async def watch_diagnostic():
    """Local read-only validation; never connects or writes AP progress."""
    game, previous, detector = None, None, VictoryDetector()
    try:
        while True:
            try:
                if game is None:
                    game = GameMemory.find()
                    if game is None:
                        LOG.info("Waiting for the Steam Zero Hour game...")
                        await asyncio.sleep(5)
                        continue
                    LOG.info("Attached to %s (PID %d)", game.path, game.pid)
                snapshot = game.snapshot()
                if snapshot is not None:
                    if snapshot != previous:
                        LOG.info("Game state: %s", snapshot)
                        previous = snapshot
                    location = detector.observe(snapshot)
                    if location:
                        LOG.info("DETECTED VICTORY: %s (diagnostic only)", BY_ID[location]["name"])
            except MemoryReadError as error:
                LOG.warning("%s", error)
                if game:
                    game.close()
                    game = None
                detector.reset()
                await asyncio.sleep(5)
            await asyncio.sleep(0.1)
    finally:
        if game:
            game.close()


async def send_test_deathlink(server, slot, password=None):
    """Explicit, user-launched diagnostic; uses the release's separate test slot."""
    async with connect(server_url(server), open_timeout=15) as socket:
        async def perform():
            async for raw in socket:
                for packet in json.loads(raw):
                    if packet.get('cmd') == 'RoomInfo':
                        await socket.send(json.dumps([{'cmd':'Connect', 'game':GAME,
                            'name':slot, 'password':password, 'uuid':str(uuid.uuid4()),
                            'version':{'major':0,'minor':6,'build':7,'class':'Version'},
                            'items_handling':0, 'tags':['AP','DeathLink'], 'slot_data':True}]))
                    elif packet.get('cmd') == 'ConnectionRefused':
                        raise IncompatibleRoom('Test sender refused: '+', '.join(packet.get('errors', [])))
                    elif packet.get('cmd') == 'Connected':
                        await socket.send(json.dumps([{'cmd':'Bounce','tags':['DeathLink'],
                            'data':{'time':time.time(),'source':slot,'cause':f'{slot} sent a test DeathLink.'}}]))
                        LOG.info('Test DeathLink sent to linked players in this room.')
                        await asyncio.sleep(0.5)
                        return
        await asyncio.wait_for(perform(), 20)


def main():
    import argparse
    import os
    parser = argparse.ArgumentParser(description="Zero Hour campaign and Generals Challenge checks for Archipelago")
    parser.add_argument('--version', action='version', version=f'Zero Hour Archipelago {VERSION} - {SUPPORT_TARGET}')
    parser.add_argument('--check-executable', type=Path, metavar='GAME_DAT',
                        help='Check an executable on disk and print a compatibility report; no game writes or server connection')
    parser.add_argument("--server", help="Archipelago host:port (or ws:// / wss:// URL)")
    parser.add_argument("--slot", help="Slot name from your player YAML")
    parser.add_argument("--password", action="store_true", help="Prompt securely for the room password")
    parser.add_argument("--state-dir", type=Path, default=Path(os.environ.get("LOCALAPPDATA", ".")) / "ZeroHourArchipelago" / "progress")
    parser.add_argument("--watch", action="store_true", help="Watch victories locally without a server or checks")
    parser.add_argument("--diagnose", action="store_true", help="Print one game snapshot and exit")
    parser.add_argument("--diagnose-dozer", action="store_true", help="Inspect the Dozer restriction without changing it")
    parser.add_argument("--diagnose-builders", action="store_true", help="Inspect cross-faction builder menus without changing them")
    parser.add_argument("--diagnose-effects", action="store_true", help="Inspect local-player cash and energy without changing them")
    parser.add_argument('--diagnose-deathlink', action='store_true', help='Inspect mission failure and restart layout without changing it')
    parser.add_argument('--send-deathlink-test', action='store_true', help='Send one DeathLink to linked players; use the separate DeathLinkTester slot')
    args = parser.parse_args()
    logging.basicConfig(level=logging.INFO, format="%(asctime)s %(message)s", datefmt="%H:%M:%S")
    try:
        if args.check_executable:
            from .compatibility_report import executable_report
            report = executable_report(args.check_executable)
            print(json.dumps(report, indent=2))
            return 0 if report['native_layout_verified'] else 1
        if args.diagnose or args.diagnose_dozer or args.diagnose_builders or args.diagnose_effects or args.diagnose_deathlink:
            game = GameMemory.find()
            if game is None:
                LOG.info("Game is not running. Start Zero Hour through Steam, then retry.")
                return 1
            try:
                LOG.info("Validated game: %s; snapshot: %s", game.path, game.snapshot())
                if args.diagnose_deathlink:
                    LOG.info('DeathLink mission state: %s', mission_state(game))
                    client = game.pointer(game.base + GAME_CLIENT_RVA)
                    LOG.info('GameClient: %s; vtable: %s', hex(client), hex(game.pointer(client)) if client else 'none')
                if args.diagnose_effects:
                    state = PlayerEffects(game, None).snapshot()
                    LOG.info("Effect state: %s", state)
                    if state and state.player:
                        LOG.info("Cash: %d; natural power production: %d; consumption: %d; sabotage expiry frame: %d",
                                 game.pointer(state.player + 0x38), game.pointer(state.player + 0x84),
                                 game.pointer(state.player + 0x88), game.pointer(state.player + 0x8C))
                if args.diagnose_builders:
                    adapter = BuilderUnlock(game)
                    LOG.info("Builder context: %s", adapter.context())
                    sets, buttons = adapter.menus()
                    LOG.info("Builder buttons: %s", {n: hex(buttons[n]) for n in BUTTON_NAMES if n in buttons})
                    for name, slots in MENUS.items():
                        if name in sets:
                            LOG.info("%s: %s", name, {slot + 1: hex(game.pointer(sets[name] + 0x10 + slot * 4)) for slot in slots})
                if args.diagnose_dozer:
                    dozer = DozerUnlock(game)
                    logic = dozer.active_logic()
                    if logic is None:
                        LOG.info("Start USA Mission 1 to inspect its Dozer restriction.")
                    else:
                        slot = dozer.find_slot(logic)
                        button = dozer.original_button()
                        LOG.info("Dozer override address: %s; original button: %s; current value: %s",
                                 hex(slot) if slot else None, hex(button) if button else None,
                                 hex(game.pointer(slot)) if slot else None)
            finally:
                game.close()
            return 0
        if args.watch:
            asyncio.run(watch_diagnostic())
        else:
            server = args.server or input("Archipelago server (host:port): ").strip()
            slot = args.slot or input("Slot name [ZeroHour]: ").strip() or "ZeroHour"
            password = getpass.getpass("Room password: ") if args.password else None
            if args.send_deathlink_test:
                asyncio.run(send_test_deathlink(server, slot, password))
                return 0
            LOG.info("Zero Hour: campaign and Generals Challenge checks. Keep this client open while playing.")
            asyncio.run(ZeroHourClient(server, slot, password, args.state_dir).run())
        return 0
    except (KeyboardInterrupt, EOFError):
        LOG.info("Client stopped. Recorded checks are saved.")
        return 0
    except Exception as error:
        LOG.error("%s", error)
        return 1
