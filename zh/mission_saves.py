"""Zero Hour mission-start saves: metadata and campaign state, never a snapshot.

Layout follows GameState v2, CampaignManager v5, SkirmishGameInfo v4 and
Money v1 in the published engine source, checked against native Steam saves.
"""
from dataclasses import dataclass
from datetime import datetime
import struct

from .mission_data import ALL_MISSIONS

DIFFICULTIES = ('Easy', 'Medium', 'Hard')
# Indices in stock INIZH.big Data/INI/PlayerTemplate.ini, including Civilian and Observer.
GENERALS = {
    'challenge_0': ('Air', 7, 'USA Air Force General'),
    'challenge_1': ('Toxin', 11, 'GLA Toxin General'),
    'challenge_2': ('Nuclear', 10, 'China Nuclear General'),
    'challenge_3': ('Superweapon', 5, 'USA Superweapon General'),
    'challenge_4': ('Tank', 8, 'China Tank General'),
    'challenge_5': ('Laser', 6, 'USA Laser General'),
    'challenge_6': ('Stealth', 13, 'GLA Stealth General'),
    'challenge_7': ('Infantry', 9, 'China Infantry General'),
    'challenge_8': ('Demolition', 12, 'GLA Demolition General'),
}
OPPONENTS = {'gc_airgeneral': 'Air', 'gc_chemgeneral': 'Toxin', 'gc_nukegeneral': 'Nuclear',
             'gc_superweaponsgeneral': 'Superweapon', 'gc_tankgeneral': 'Tank',
             'gc_stealth': 'Stealth', 'gc_lasergeneral': 'Laser', 'gc_chinaboss': 'Leang'}
# Inter-mission rank carry baselines observed in native mission-start saves.
# First missions use the fresh-campaign value; no money or army is carried here.
STORY_RANKS = {'usa': (0, 0, 800, 1500, 5000), 'china': (0, 1500, 1500, 2500, 5000),
               'gla': (0, 800, 800, 0, 0)}


def ascii_string(value):
    data = value.encode('ascii')
    if len(data) > 255:
        raise ValueError('Native string is too long')
    return bytes([len(data)]) + data


def unicode_string(value):
    data = value.encode('utf-16le')
    if len(data) // 2 > 255:
        raise ValueError('Native description is too long')
    return bytes([len(data) // 2]) + data


class Reader:
    def __init__(self, data):
        self.data, self.offset = data, 0

    def take(self, size):
        if size < 0 or self.offset + size > len(self.data):
            raise ValueError('Truncated save')
        value = self.data[self.offset:self.offset + size]
        self.offset += size
        return value

    def unpack(self, fmt):
        return struct.unpack(fmt, self.take(struct.calcsize(fmt)))

    def byte(self):
        return self.take(1)[0]

    def integer(self):
        return self.unpack('<i')[0]

    def ascii(self):
        return self.take(self.byte()).decode('ascii')

    def unicode(self):
        return self.take(self.byte() * 2).decode('utf-16le')

    def end(self):
        if self.offset != len(self.data):
            raise ValueError('Unexpected trailing save data')


@dataclass(frozen=True)
class MissionSave:
    map_name: str
    date: tuple
    description: str
    map_label: str
    campaign: str
    mission_index: int
    mission: str
    rank_points: int
    difficulty: int
    challenge_data: bytes = b''
    player_template: int = 0

    def encode(self):
        if not 0 <= self.difficulty < 3:
            raise ValueError('Invalid difficulty')
        header = (b'\x02' + struct.pack('<i', 1) + ascii_string(self.map_name)
                  + struct.pack('<8H', *self.date) + unicode_string(self.description)
                  + ascii_string(self.map_label) + ascii_string(self.campaign)
                  + struct.pack('<i', self.mission_index))
        campaign = (b'\x05' + ascii_string(self.campaign) + ascii_string(self.mission)
                    + struct.pack('<iiB', self.rank_points, self.difficulty, bool(self.challenge_data))
                    + self.challenge_data + struct.pack('<i', self.player_template))
        return b''.join(ascii_string(name) + struct.pack('<I', len(data)) + data
                        for name, data in (('CHUNK_GameState', header), ('CHUNK_Campaign', campaign))) + ascii_string('SG_EOF')

    @classmethod
    def decode(cls, data):
        r = Reader(data)
        chunks = []
        for expected in ('CHUNK_GameState', 'CHUNK_Campaign'):
            if r.ascii() != expected:
                raise ValueError('Not a mission-start save')
            chunks.append(Reader(r.take(r.unpack('<I')[0])))
        if r.ascii() != 'SG_EOF':
            raise ValueError('Unexpected snapshot chunks')
        r.end()
        h, c = chunks
        if h.byte() != 2 or h.integer() != 1:
            raise ValueError('Not native mission-start format v2')
        map_name, date, description = h.ascii(), h.unpack('<8H'), h.unicode()
        label, campaign, index = h.ascii(), h.ascii(), h.integer()
        h.end()
        if c.byte() != 5 or c.ascii() != campaign:
            raise ValueError('Unsupported campaign state')
        mission, rank, difficulty, challenge = c.ascii(), c.integer(), c.integer(), c.byte()
        if challenge not in (0, 1) or not 0 <= difficulty <= 2:
            raise ValueError('Invalid campaign values')
        challenge_data = c.take(len(c.data) - c.offset - 4) if challenge else b''
        if challenge_data:
            parse_challenge(challenge_data)
        template = c.integer()
        c.end()
        return cls(map_name, date, description, label, campaign, index, mission,
                   rank, difficulty, challenge_data, template)


def parse_challenge(data):
    r = Reader(data)
    if r.byte() != 4:
        raise ValueError('Unsupported challenge state version')
    header = r.unpack('<iiBBBi')
    if r.integer() != 8:
        raise ValueError('Challenge must have eight slots')
    slots = []
    for _ in range(8):
        slots.append((r.integer(), r.unicode(), r.unpack('<BB'), r.unpack('<7i')))
    local_ip, map_name = r.integer(), r.ascii()
    map_values, superweapons = r.unpack('<4i'), r.unpack('<H')[0]
    if r.byte() != 1:
        raise ValueError('Unsupported Money state')
    cash = r.unpack('<I')[0]
    r.end()
    return dict(header=header, slots=slots, local_ip=local_ip, map=map_name,
                map_values=map_values, superweapons=superweapons, cash=cash)


def make_challenge(campaign, map_name):
    _, template, name = GENERALS[campaign]
    # One accepted local human; all other lobby slots closed. The actual enemy,
    # script state, units and cash are created from the stock mission map.
    data = b'\x04' + struct.pack('<iiBBBi', 0, 100, 1, 0, 0, 0) + struct.pack('<i', 8)
    data += (struct.pack('<i', 5) + unicode_string(name) + b'\x01\x00'
             + struct.pack('<7i', 5, 0, template, -1, -1, -1, template))
    closed = struct.pack('<i', 1) + unicode_string('Closed') + b'\x00\x00' + struct.pack('<7i', *([-1] * 7))
    data += closed * 7
    data += struct.pack('<i', 0) + ascii_string(map_name)
    data += struct.pack('<4iHBI', 0, 0, 7, 0, 0, 1, 10000)
    return data


def create_save(mission, difficulty, timestamp=None):
    if difficulty not in DIFFICULTIES:
        raise ValueError('Unknown difficulty')
    timestamp = timestamp or datetime.now()
    campaign = mission['campaign']
    number = int(mission['mission'].removeprefix('mission'))
    map_name = mission['map'].replace('/', '\\')
    challenge, template = b'', 0
    if campaign in GENERALS:
        short, template, _ = GENERALS[campaign]
        opponent = OPPONENTS[mission['map'].split('/')[-2]]
        label = f'{short} {number} - Vs. {opponent}'
        challenge = make_challenge(campaign, map_name)
        rank = 0 if number == 1 else 5000
    else:
        label = f'{dict(usa="USA", china="China", gla="GLA")[campaign]} {number}'
        rank = STORY_RANKS[campaign][number - 1]
    title = f'Archipelago - {difficulty} - {label}'
    date = (timestamp.year, timestamp.month, timestamp.day, (timestamp.weekday() + 1) % 7,
            timestamp.hour, timestamp.minute, timestamp.second, timestamp.microsecond // 1000)
    return MissionSave(map_name, date, title, map_name.rsplit('\\', 1)[-1], campaign,
                       number - 1, mission['mission'], rank, DIFFICULTIES.index(difficulty), challenge, template)


def all_saves(timestamp=None):
    timestamp = timestamp or datetime.now()
    return [(difficulty, create_save(mission, difficulty, timestamp))
            for difficulty in DIFFICULTIES for mission in ALL_MISSIONS]
