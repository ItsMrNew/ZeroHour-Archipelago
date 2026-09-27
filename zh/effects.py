"""Local-player cash and native timed power sabotage for the verified Steam build."""
from dataclasses import dataclass

from .dozer import GAME_LOGIC_RVA
from .memory import MemoryReadError
from .mission_data import ALL_BY_CAMPAIGN_MISSION, CASH_ITEM_ID, POWER_TRAP_ID
from .power import PowerOutage
from .gameplay import input_enabled
from .consumables import CombatEffects
from .mission_data import SUPPLY_DROP_ID, CASH_THEFT_ID, REINFORCEMENTS_ID, PRODUCTION_SHUTDOWN_ID, SELL_BUILDING_ID

PLAYER_LIST_RVA = 0x6395A0
MONEY_VTABLE_RVA = 0x5456F0
ENERGY_VTABLE_RVA = 0x54F758
FRAMES_PER_SECOND = 30


@dataclass(frozen=True)
class EffectState:
    logic: int
    frame: int
    loading_map: bool
    loading_save: bool
    player: int = 0
    mission: tuple = ()


class PlayerEffects:
    def __init__(self, game, progress, expanded=False, sell_refund='normal_refund', generals=False, options=None):
        from .game_options import DEFAULTS
        self.options = {**DEFAULTS, **(options or {})}
        self.game, self.progress = game, progress
        self.loading = False
        self.save_load = False
        self.start_pending = False
        self.power = CombatEffects(game, generals=True) if generals else None
        from .generals_points import GeneralsPoints
        self.generals = GeneralsPoints(self) if generals else None
        self.cash_ready_since = None
        self.cash_deferred = False
        self.cash_waiting = False
        self.start_key = None
        self.expanded = expanded
        self.sell_refund = sell_refund

    def configure_power(self):
        self.power.power_seconds = self.options["power_outage_seconds"]
        self.power.production_seconds = self.options["production_shutdown_seconds"]

    def clear_transient(self):
        if isinstance(self.power, CombatEffects):
            self.power.clear_transient()

    def close(self):
        try:
            if self.generals:
                self.generals.close()
        finally:
            if self.power:
                self.power.close()

    def snapshot(self):
        logic = self.game.pointer(self.game.base + GAME_LOGIC_RVA)
        if not logic:
            return None
        flags = self.game.read(logic + 0x51, 2)
        if any(value not in (0, 1) for value in flags):
            raise MemoryReadError('Invalid game loading flags.')
        frame = self.game.pointer(logic + 0x3C)
        if any(flags):
            return EffectState(logic, frame, bool(flags[0]), bool(flags[1]))
        mission = self.game.snapshot()
        if mission is None:
            return None
        definition = ALL_BY_CAMPAIGN_MISSION.get((mission.campaign, mission.mission))
        if (self.game.pointer(logic + 0x94) != 0 or not definition or mission.victorious
                or mission.map_name != definition['map']):
            return EffectState(logic, frame, False, False)
        players = self.game.pointer(self.game.base + PLAYER_LIST_RVA)
        if not players:
            return None
        player = self.game.pointer(players + 0xC)
        if not player:
            return None
        index = self.game.pointer(player + 0x24)
        count = self.game.pointer(players + 0x10)
        if index == 0:
            return None  # Neutral player while the scene is being prepared.
        if not 0 < index < count <= 16 or self.game.pointer(players + 0x14 + index * 4) != player:
            raise MemoryReadError('Local player identity does not match the player list.')
        # Player::init first sets Money's audio/player index, then can overwrite
        # it by copying the default starting-cash Money (whose index is zero).
        # Steam VA 0x450610 copies both amount and index. It is not an ownership
        # pointer; actual identity is checked via PlayerList and Energy below.
        fields = (
            ('Money vtable', player + 0x34, (self.game.base + MONEY_VTABLE_RVA,)),
            ('Money audio player index', player + 0x3C, (0, index)),
            ('Energy vtable', player + 0x80, (self.game.base + ENERGY_VTABLE_RVA,)),
            ('Energy owner', player + 0x90, (player,)),
        )
        mismatches = []
        for name, address, expected in fields:
            actual = self.game.pointer(address)
            if actual not in expected:
                mismatches.append(f'{name}: read {actual:#x}, expected '
                                  + ' or '.join(f'{value:#x}' for value in expected))
        if mismatches:
            raise MemoryReadError('Local player layout mismatch: ' + '; '.join(mismatches))
        return EffectState(logic, frame, False, False, player, (mission.campaign, mission.mission))

    def check_same(self, state):
        fresh = self.snapshot()
        if (fresh is None or not fresh.player or fresh.loading_map or fresh.loading_save
                or (fresh.logic, fresh.player, fresh.mission) != (state.logic, state.player, state.mission)
                or fresh.frame < state.frame):
            raise MemoryReadError('Mission changed before item effect; waiting.')

    def apply(self, inventory):
        messages = self.power.poll() if self.power else []
        pending_cash = [i for i, item in enumerate(inventory.items)
                        if item.item == CASH_ITEM_ID and i not in self.progress.effect_receipts]
        pending_consumable_cash = [i for i, item in enumerate(inventory.items)
            if self.expanded and item.item in (SUPPLY_DROP_ID, CASH_THEFT_ID)
            and i not in self.progress.effect_receipts]
        self.cash_waiting = bool(self.start_pending or pending_cash or pending_consumable_cash)
        state = self.snapshot()
        if self.generals:
            messages.extend(self.generals.apply(state, inventory))
        if state is None:
            return messages
        tiers = inventory.count(CASH_ITEM_ID)
        if state.loading_map or state.loading_save:
            self.loading = True
            self.save_load |= state.loading_save
            self.start_pending = False
            self.start_key = self.cash_ready_since = None
            self.cash_deferred = False
            return messages
        if self.loading:
            self.start_pending = not self.save_load and state.frame <= 150
            self.loading = self.save_load = False
        if not state.player:
            if state.frame > 150:
                self.start_pending = False
                self.start_key = self.cash_ready_since = None
            return messages
        key = (state.logic, state.mission)
        if self.start_pending:
            if self.start_key is not None and self.start_key != key:
                self.start_pending = False
                self.cash_ready_since = None
            else:
                self.start_key = key
        # Opening scripts can set money long after frame 30. Wait for control.
        if state.frame < 30:
            return messages
        pending_traps = [i for i, item in enumerate(inventory.items)
                         if item.item == POWER_TRAP_ID and i not in self.progress.effect_receipts]
        cash_due = bool(self.start_pending or pending_cash or pending_consumable_cash)
        self.cash_waiting = cash_due
        cash_ready = False
        if cash_due:
            if not input_enabled(self.game):
                if not self.cash_deferred:
                    messages.append('Cash bonus waiting for player control after the opening or pause.')
                self.cash_ready_since = None
                self.cash_deferred = True
            elif self.start_pending or self.cash_deferred:
                if self.cash_ready_since is None or state.frame < self.cash_ready_since:
                    self.cash_ready_since = state.frame
                cash_ready = state.frame - self.cash_ready_since >= FRAMES_PER_SECOND
            else:
                cash_ready = True  # normal mid-mission receipt stays immediate
        if cash_ready:
            # Existing tiers add the mission bonus. Unconsumed cash receipts
            # each grant once, even if they arrived while the map was loading.
            existing = sum(item.item == CASH_ITEM_ID and i in self.progress.effect_receipts
                           for i, item in enumerate(inventory.items))
            bonus = 5000 * ((existing if self.start_pending else 0) + len(pending_cash))
            self.check_same(state)
            if not input_enabled(self.game):
                self.cash_ready_since = None
                self.cash_deferred = True
                return messages
            amount = self.game.pointer(state.player + 0x38)
            if amount + bonus > 0xFFFFFFFF:
                raise MemoryReadError('Cash bonus would overflow the game balance; left unchanged.')
            was_start = self.start_pending
            self.start_pending = False
            self.cash_waiting = self.cash_deferred = False
            self.cash_ready_since = self.start_key = None
            if bonus:
                self.progress.reserve_effects(pending_cash)
                try:
                    self.game.replace_pointer(state.player + 0x38, amount, amount + bonus)
                except MemoryReadError as error:
                    raise MemoryReadError('Cash write uncertain; receipt reserved to prevent duplicate money. ' + str(error)) from error
                messages.append(f'{"Mission starting cash" if was_start else "Cash item"}: +${bonus:,}. Future start bonus: ${tiers * 5000:,}.')
            # One-shot receipts are applied in their AP order. Theft is a flat
            # quarter of the balance at application time, rounded down to $1.
            for index in pending_consumable_cash:
                self.check_same(state)
                if not input_enabled(self.game):
                    self.cash_deferred = self.cash_waiting = True
                    break
                amount = self.game.pointer(state.player + 0x38)
                supply = inventory.items[index].item == SUPPLY_DROP_ID
                delta = 5000 if supply else -(amount * self.options["cash_theft_percent"] // 100)
                if amount + delta > 0xFFFFFFFF:
                    raise MemoryReadError('Supply Drop would overflow the game balance; waiting.')
                self.progress.reserve_effects([index])
                try:
                    self.game.replace_pointer(state.player + 0x38, amount, amount + delta)
                except MemoryReadError as error:
                    raise MemoryReadError('Consumable cash write uncertain; receipt reserved to prevent replay. ' + str(error)) from error
                messages.append('Supply Drop: +$5,000 (one-time).' if supply else
                                f'Cash Theft: -${-delta:,} ({self.options["cash_theft_percent"]}%, no cap). Balance: ${amount + delta:,}.')
        if pending_traps and input_enabled(self.game):
            if self.power is None:
                self.power = CombatEffects(self.game) if self.expanded else PowerOutage(self.game)
            if self.power.busy:
                return messages
            self.check_same(state)
            self.configure_power()
            self.power.prepare(state, len(pending_traps))
            self.check_same(state)
            self.progress.reserve_effects(pending_traps)
            try:
                self.power.arm()
            except MemoryReadError as error:
                raise MemoryReadError('Power trap write uncertain; receipt reserved to prevent replay. ' + str(error)) from error
            messages.append(f'Power Outage Trap queued: {len(pending_traps) * self.options["power_outage_seconds"]} additional simulation seconds. Resume the game to apply the blackout.')
        if self.expanded and input_enabled(self.game) and not self.start_pending and not self.cash_deferred:
            pending_native = [(i, item.item) for i, item in enumerate(inventory.items)
                if item.item in (REINFORCEMENTS_ID, PRODUCTION_SHUTDOWN_ID, SELL_BUILDING_ID)
                and i not in self.progress.effect_receipts]
            if pending_native:
                if self.power is None:
                    self.power = CombatEffects(self.game)
                if not self.power.busy:
                    index, item = pending_native[0]
                    self.check_same(state)
                    operation, name = {REINFORCEMENTS_ID: (1, 'Reinforcements'),
                        PRODUCTION_SHUTDOWN_ID: (2, 'Production Shutdown'),
                        SELL_BUILDING_ID: (5, 'Sell Random Building')}[item]
                    self.configure_power()
                    self.power.prepare(state, 1, operation)
                    if operation == 5:
                        self.power.prepare_sale_refund(self.sell_refund)
                    self.check_same(state)
                    self.progress.reserve_effects([index])
                    self.power.arm()
                    messages.append(name + ' queued for the next simulation update.')
        return messages
