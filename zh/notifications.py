"""Live AP item-transfer feed, independent of simulation time and inventory replay."""
from collections import deque
import re
import time
import unicodedata

from .mission_data import (GAME, ITEM_NAMES, SET_ITEMS, ALL_BUILDER_ITEMS,
    GENERALS_ITEMS, ABILITY_ITEMS, CASH_ITEM_ID, REINFORCEMENTS_ID, SUPPLY_DROP_ID, ITEM_ID,
    POWER_TRAP_ID, CASH_THEFT_ID, PRODUCTION_SHUTDOWN_ID, SELL_BUILDING_ID)

DEFAULT_NOTIFICATIONS = {'scope': 'you', 'seconds': 8}
# Archipelago NetUtils.JSONtoTextParser colours and flag precedence. These bits
# are native-menu presentation flags, not AP's item flags.
ITEM_COLOURS = ((1, 128, 0xFFAF99EF), (2, 256, 0xFF6D8BE8),
                (4, 512, 0xFFFA8072), (0, 1024, 0xFF00EEEE))


def item_colour(flags):
    return '#%06X' % next(colour & 0xffffff for mask, _, colour in ITEM_COLOURS
                         if not mask or flags & mask)


def local_item_flags(item):
    if isinstance(item, str):
        item = next((code for code, name in ITEM_NAMES.items() if name == item), None)
    if item in SET_ITEMS:
        return 1
    if item in (POWER_TRAP_ID, CASH_THEFT_ID, PRODUCTION_SHUTDOWN_ID, SELL_BUILDING_ID):
        return 4
    if (item in ALL_BUILDER_ITEMS or item in GENERALS_ITEMS or item in ABILITY_ITEMS
            or item == CASH_ITEM_ID):
        return 2
    return 0


def validate_settings(value):
    if (not isinstance(value, dict) or set(value) != set(DEFAULT_NOTIFICATIONS)
            or value['scope'] not in ('you', 'all', 'off')
            or type(value['seconds']) is not int or not 1 <= value['seconds'] <= 60):
        raise ValueError('Invalid notification preferences.')
    return dict(value)


def safe_text(text, limit=63):
    text = unicodedata.normalize('NFKD', str(text)).encode('ascii', 'replace').decode()
    text = ' '.join(text.split())
    return text if len(text) <= limit else text[:limit-3] + '...'


class ItemNotifications:
    def __init__(self, clock=time.monotonic):
        self.clock = clock
        self.players, self.slots = {}, {}
        self.items = {GAME: dict(ITEM_NAMES)}
        self.queue = deque(maxlen=256)
        self.active = deque()
        self.seen = set()
        self.settings = dict(DEFAULT_NOTIFICATIONS)
        self.team, self.slot = 0, 0

    def connected(self, packet, settings):
        self.team, self.slot = packet['team'], packet['slot']
        self.update_players(packet.get('players', []))
        self.slots.update({int(k): v for k, v in packet.get('slot_info', {}).items()})
        self.configure(settings)
        return sorted({v['game'] for v in self.slots.values() if v.get('game')})

    def update_players(self, players):
        for player in players:
            if isinstance(player, dict) and player.get('team') == self.team:
                self.players[player['slot']] = player.get('alias') or player.get('name') or str(player['slot'])

    def data_package(self, packet):
        for game, data in packet.get('data', {}).get('games', {}).items():
            self.items[game] = {code: name for name, code in data.get('item_name_to_id', {}).items()}

    def configure(self, settings):
        settings = validate_settings(settings)
        self.settings = settings
        self.queue = deque((event for event in self.queue if self.accepts(event)), maxlen=256)
        self.active = deque((event, start) for event, start in self.active if self.accepts(event))

    def accepts(self, event):
        return self.settings['scope'] == 'all' or (self.settings['scope'] == 'you'
            and (self.slot in (event[0], event[1]) or self.slot in self.slots.get(event[1], {}).get('group_members', [])))

    def receive(self, packet):
        if packet.get('type') is None:
            return self.receive_server_send(packet)
        if packet.get('type') not in ('ItemSend', 'ItemCheat'):
            return
        if packet.get('team', self.team) != self.team:
            return
        item, recipient = packet.get('item'), packet.get('receiving')
        if not isinstance(item, dict) or type(recipient) is not int:
            return
        if any(type(item.get(k)) is not int for k in ('player', 'item', 'location')):
            return
        flags = item.get('flags', 0)
        flags = flags if type(flags) is int else 0
        game = self.slots.get(recipient, {}).get('game', GAME if recipient == self.slot else '')
        # Server cheats can omit classification, even in structured notices.
        if packet['type'] == 'ItemCheat' and not flags and game == GAME:
            flags = local_item_flags(item['item'])
        # Old rooms retain their generated useful flags. Correct these three
        # local filler colours immediately without reclassifying other games.
        if game == GAME and item['item'] in (ITEM_ID, REINFORCEMENTS_ID, SUPPLY_DROP_ID):
            flags = 0
        event = (item['player'], recipient, item['item'], item['location'], flags)
        # Real locations are unique. Cheat deliveries (-1) can legitimately repeat.
        if item['location'] >= 0:
            if event[:4] in self.seen:
                return
            self.seen.add(event[:4])
        if self.accepts(event):
            self.queue.append(event)
        return event

    def receive_server_send(self, packet):
        """AP 0.6.7 /send[_multiple] lacks ItemCheat metadata (unlike !getitem).

        Parse only the server's exact single-text notice. Do not derive toasts
        from ReceivedItems: that would replay inventory and duplicate transfers.
        """
        if packet.get('cmd') != 'PrintJSON' or packet.get('team', self.team) != self.team:
            return
        parts = packet.get('data')
        if (not isinstance(parts, list) or len(parts) != 1 or not isinstance(parts[0], dict)
                or parts[0].get('type', 'text') != 'text' or not isinstance(parts[0].get('text'), str)):
            return
        match = re.fullmatch(r'Cheat console: sending (?:(\d{1,3}) of )?"(.+)" to (.+)', parts[0]['text'])
        if not match:
            return
        count, item, recipient_name = match.groups()
        count = int(count or '1')
        if not 1 <= count <= 100:
            return
        # get_aliased_name emits either the slot name or "Alias (Slot name)".
        matches = []
        for slot in set(self.slots) | set(self.players):
            original = self.slots.get(slot, {}).get('name')
            alias = self.players.get(slot)
            names = {name for name in (original, alias, f'{alias} ({original})' if alias and original else None) if name}
            if recipient_name in names:
                matches.append(slot)
        if len(matches) != 1:
            return  # Do not attribute an ambiguous player name to the wrong slot.
        recipient = matches[0]
        game = self.slots.get(recipient, {}).get('game', GAME if recipient == self.slot else '')
        flags = local_item_flags(item) if game == GAME else 0
        event = (0, recipient, item if count == 1 else f'{item} x{count}', -1, flags)
        if self.accepts(event):
            self.queue.append(event)
        return event

    def name(self, slot):
        return self.players.get(slot, self.slots.get(slot, {}).get('name', 'Server' if slot == 0 else f'Player {slot}'))

    def log_parts(self, event):
        sender, recipient, item, _, flags = event
        game = self.slots.get(recipient, {}).get('game', GAME if recipient == self.slot else '')
        name = item if isinstance(item, str) else self.items.get(game, {}).get(item, f'Item {item}')
        return [(f'{self.name(sender)} sent ', None), (name, item_colour(flags)),
                (f' to {self.name(recipient)}', None)]

    def lines(self):
        now = self.clock()
        self.active = deque((event, start) for event, start in self.active
                            if now-start < self.settings['seconds'])
        while len(self.active) < 2 and self.queue:
            self.active.append((self.queue.popleft(), now))
        result = []
        for (sender, recipient, item, _, flags), _start in self.active:
            game = self.slots.get(recipient, {}).get('game', GAME if recipient == self.slot else '')
            name = item if isinstance(item, str) else self.items.get(game, {}).get(item, f'Item {item}')
            result.extend((f'{safe_text(self.name(sender), 40)} sent',
                           safe_text(name, 48), f'to {safe_text(self.name(recipient), 40)}'))
        return result + [''] * (6-len(result))

    def labels(self):
        settings = self.settings
        labels = {8: ('Notifications', 1), 70: ('Item transfers: choose which players to show.', 0),
                  74: (f'Display duration: {settings["seconds"]} seconds', 0),
                  75: ('-1 second', 1), 76: ('+1 second', 1),
                  77: ('Shown during play, while paused and at the main menu.', 0)}
        for ident, scope, text in ((71, 'you', 'Your items'), (72, 'all', 'All players'), (73, 'off', 'Off')):
            labels[ident] = (text, 3 if settings['scope'] == scope else 1)
        lines = self.lines()
        for i, line in enumerate(lines):
            flags = 8 if line else 4 | 8  # Bold, high-contrast compact cards.
            if line and i % 3 == 1:
                item_flags = self.active[i // 3][0][4]
                flags |= next(style for mask, style, _ in ITEM_COLOURS if not mask or item_flags & mask)
            labels[80+i] = (line, flags)
        return labels

    def selection(self, event):
        settings = dict(self.settings)
        if event in (71, 72, 73):
            settings['scope'] = {71:'you', 72:'all', 73:'off'}[event]
        elif event in (75, 76):
            settings['seconds'] = max(1, min(60, settings['seconds'] + (-1 if event == 75 else 1)))
        return settings
