"""Shared, stable mission and builder item IDs."""

GAME = "Command & Conquer: Generals - Zero Hour"
PROTOCOL_VERSION = 17
BASE_ID = 0x5A4800
REVEAL_MINIMAP_ID = BASE_ID + 0x130
CARPET_BOMB_ID = BASE_ID + 0x131
PATRIOT_AIRDROP_ID = BASE_ID + 0x132
GENERALS_POINT_ID = BASE_ID + 0x133
EMERGENCY_REPAIR_ID = BASE_ID + 0x134
GENERALS_POINT_NAME = 'Progressive Generals Point'
GENERALS_ITEMS = {GENERALS_POINT_ID: GENERALS_POINT_NAME}
GENERALS_POINTS_MAX = 18
GENERALS_POINTS_LIMIT = GENERALS_POINTS_MAX + 10
GENERALS_CONFIG = {'rank_thresholds': [1, 2, 3, 4, 7], 'budget': 'received_minus_mission_spent'}
ABILITY_ITEMS = {REVEAL_MINIMAP_ID: 'Reveal Minimap', CARPET_BOMB_ID: 'Carpet Bomb', PATRIOT_AIRDROP_ID: 'Patriot Airdrop', EMERGENCY_REPAIR_ID: 'Emergency Repair'}
LEGACY_ABILITY_CONFIG = {'reveal_seconds': 15, 'reveal_cooldown': 180, 'carpet_cooldown': 240}
PATRIOT_ABILITY_CONFIG = {**LEGACY_ABILITY_CONFIG, 'patriot_cooldown': 300, 'patriot_count': 3}
ABILITY_CONFIG = {**PATRIOT_ABILITY_CONFIG, 'repair_level': 3, 'repair_amount': 300,
                  'repair_radius': 100, 'repair_cooldown': 240}
ITEM_NAME = "Mission Report"
ITEM_ID = BASE_ID
DOZER_ITEM_NAME = "USA Dozer"
DOZER_ITEM_ID = BASE_ID + 0x100
CHINA_DOZER_ITEM_ID = BASE_ID + 0x101
GLA_WORKER_ITEM_ID = BASE_ID + 0x102
BUILDER_ITEMS = {DOZER_ITEM_ID: DOZER_ITEM_NAME, CHINA_DOZER_ITEM_ID: "China Dozer", GLA_WORKER_ITEM_ID: "GLA Worker"}
# Keep the three original IDs and their legacy protocol meaning unchanged.
GENERAL_BUILDERS = (
    ('USA Air Force Dozer', 'usa', 'airf_command_constructamericadozer'),
    ('USA Laser Dozer', 'usa', 'lazr_command_constructamericadozer'),
    ('USA Superweapon Dozer', 'usa', 'supw_command_constructamericadozer'),
    ('China Infantry Dozer', 'china', 'infa_command_constructchinadozer'),
    ('China Nuclear Dozer', 'china', 'nuke_command_constructchinadozer'),
    ('China Tank Dozer', 'china', 'tank_command_constructchinadozer'),
    ('GLA Demolition Worker', 'gla', 'demo_command_constructglaworker'),
    ('GLA Stealth Worker', 'gla', 'slth_command_constructglaworker'),
    ('GLA Toxin Worker', 'gla', 'chem_command_constructglaworker'),
)
BUILDER_CATALOG = {
    DOZER_ITEM_ID: ('USA Dozer', 'usa', 'command_constructamericadozer'),
    CHINA_DOZER_ITEM_ID: ('China Dozer', 'china', 'command_constructchinadozer'),
    GLA_WORKER_ITEM_ID: ('GLA Worker', 'gla', 'command_constructglaworker'),
    **{BASE_ID + 0x120 + i: value for i, value in enumerate(GENERAL_BUILDERS)},
}
ALL_BUILDER_ITEMS = {item: entry[0] for item, entry in BUILDER_CATALOG.items()}
POWER_TRAP_ID = BASE_ID + 0x110
CASH_ITEM_ID = BASE_ID + 0x111
POWER_TRAP_NAME = "Power Outage Trap"
CASH_ITEM_NAME = "Progressive Starting Cash"
EFFECT_ITEMS = {POWER_TRAP_ID: POWER_TRAP_NAME, CASH_ITEM_ID: CASH_ITEM_NAME}
REINFORCEMENTS_ID = BASE_ID + 0x112
SUPPLY_DROP_ID = BASE_ID + 0x113
CASH_THEFT_ID = BASE_ID + 0x114
PRODUCTION_SHUTDOWN_ID = BASE_ID + 0x115
SELL_BUILDING_ID = BASE_ID + 0x116
CONSUMABLE_ITEMS = {REINFORCEMENTS_ID: "Reinforcements", SUPPLY_DROP_ID: "Supply Drop",
                    CASH_THEFT_ID: "Cash Theft", PRODUCTION_SHUTDOWN_ID: "Production Shutdown",
                    SELL_BUILDING_ID: "Sell Random Building"}
EFFECT_ITEMS.update(CONSUMABLE_ITEMS)
# Retain the legacy wire configuration so existing rooms remain compatible.
# Client 0.13.2 expands the three infantry to a fixed CIA/Humvee squad; the
# native recipe lives in zh.reinforcements, not in these protocol markers.
CONSUMABLE_CONFIG = {"reinforcements_infantry": 3, "supply_drop_cash": 5000,
                     "cash_theft_percent": 25, "production_shutdown_seconds": 20}
ITEM_NAMES = {ITEM_ID: ITEM_NAME, **ALL_BUILDER_ITEMS, **EFFECT_ITEMS, **ABILITY_ITEMS, **GENERALS_ITEMS}
EFFECT_CONFIG = {"power_outage_seconds": 30, "starting_cash_increment": 5000}
CAMPAIGNS = ("USA", "GLA", "China")
MISSIONS = tuple(
    {
        "key": f"{campaign.lower()}_{number:02}",
        "name": f"{campaign} Mission {number:02} - Victory",
        "campaign": campaign.lower(),
        "mission": f"mission{number:02}",
        "map": f"maps/md_{prefix}{number:02}/md_{prefix}{number:02}.map",
        "id": BASE_ID + index * 5 + number,
    }
    for index, (campaign, prefix) in enumerate(zip(CAMPAIGNS, ("usa", "gla", "chi")))
    for number in range(1, 6)
)
# Stable challenge IDs: reserve sixteen IDs for each playable general.
# Mission ordering/maps transcribed from the installed Steam Campaign.ini;
# playable general labels verified against ChallengeMode.ini.
CHALLENGE_CAMPAIGNS = (('challenge_0',
  'USA Air Force',
  (('mission01', 'maps/gc_chemgeneral/gc_chemgeneral.map', 'mission02'),
   ('mission02', 'maps/gc_nukegeneral/gc_nukegeneral.map', 'mission03'),
   ('mission03', 'maps/gc_superweaponsgeneral/gc_superweaponsgeneral.map', 'mission04'),
   ('mission04', 'maps/gc_tankgeneral/gc_tankgeneral.map', 'mission05'),
   ('mission05', 'maps/gc_stealth/gc_stealth.map', 'mission06'),
   ('mission06', 'maps/gc_lasergeneral/gc_lasergeneral.map', 'mission07'),
   ('mission07', 'maps/gc_chinaboss/gc_chinaboss.map', None))),
 ('challenge_1',
  'GLA Toxin',
  (('mission01', 'maps/gc_tankgeneral/gc_tankgeneral.map', 'mission02'),
   ('mission02', 'maps/gc_lasergeneral/gc_lasergeneral.map', 'mission03'),
   ('mission03', 'maps/gc_stealth/gc_stealth.map', 'mission04'),
   ('mission04', 'maps/gc_superweaponsgeneral/gc_superweaponsgeneral.map', 'mission05'),
   ('mission05', 'maps/gc_nukegeneral/gc_nukegeneral.map', 'mission06'),
   ('mission06', 'maps/gc_airgeneral/gc_airgeneral.map', 'mission07'),
   ('mission07', 'maps/gc_chinaboss/gc_chinaboss.map', None))),
 ('challenge_2',
  'China Nuclear',
  (('mission01', 'maps/gc_lasergeneral/gc_lasergeneral.map', 'mission02'),
   ('mission02', 'maps/gc_chemgeneral/gc_chemgeneral.map', 'mission03'),
   ('mission03', 'maps/gc_airgeneral/gc_airgeneral.map', 'mission04'),
   ('mission04', 'maps/gc_stealth/gc_stealth.map', 'mission05'),
   ('mission05', 'maps/gc_tankgeneral/gc_tankgeneral.map', 'mission06'),
   ('mission06', 'maps/gc_superweaponsgeneral/gc_superweaponsgeneral.map', 'mission07'),
   ('mission07', 'maps/gc_chinaboss/gc_chinaboss.map', None))),
 ('challenge_3',
  'USA Superweapon',
  (('mission01', 'maps/gc_tankgeneral/gc_tankgeneral.map', 'mission02'),
   ('mission02', 'maps/gc_airgeneral/gc_airgeneral.map', 'mission03'),
   ('mission03', 'maps/gc_chemgeneral/gc_chemgeneral.map', 'mission04'),
   ('mission04', 'maps/gc_lasergeneral/gc_lasergeneral.map', 'mission05'),
   ('mission05', 'maps/gc_stealth/gc_stealth.map', 'mission06'),
   ('mission06', 'maps/gc_nukegeneral/gc_nukegeneral.map', 'mission07'),
   ('mission07', 'maps/gc_chinaboss/gc_chinaboss.map', None))),
 ('challenge_4',
  'China Tank',
  (('mission01', 'maps/gc_chemgeneral/gc_chemgeneral.map', 'mission02'),
   ('mission02', 'maps/gc_airgeneral/gc_airgeneral.map', 'mission03'),
   ('mission03', 'maps/gc_nukegeneral/gc_nukegeneral.map', 'mission04'),
   ('mission04', 'maps/gc_superweaponsgeneral/gc_superweaponsgeneral.map', 'mission05'),
   ('mission05', 'maps/gc_stealth/gc_stealth.map', 'mission06'),
   ('mission06', 'maps/gc_lasergeneral/gc_lasergeneral.map', 'mission07'),
   ('mission07', 'maps/gc_chinaboss/gc_chinaboss.map', None))),
 ('challenge_5',
  'USA Laser',
  (('mission01', 'maps/gc_airgeneral/gc_airgeneral.map', 'mission02'),
   ('mission02', 'maps/gc_tankgeneral/gc_tankgeneral.map', 'mission03'),
   ('mission03', 'maps/gc_chemgeneral/gc_chemgeneral.map', 'mission04'),
   ('mission04', 'maps/gc_nukegeneral/gc_nukegeneral.map', 'mission05'),
   ('mission05', 'maps/gc_superweaponsgeneral/gc_superweaponsgeneral.map', 'mission06'),
   ('mission06', 'maps/gc_stealth/gc_stealth.map', 'mission07'),
   ('mission07', 'maps/gc_chinaboss/gc_chinaboss.map', None))),
 ('challenge_6',
  'GLA Stealth',
  (('mission01', 'maps/gc_airgeneral/gc_airgeneral.map', 'mission02'),
   ('mission02', 'maps/gc_tankgeneral/gc_tankgeneral.map', 'mission03'),
   ('mission03', 'maps/gc_superweaponsgeneral/gc_superweaponsgeneral.map', 'mission04'),
   ('mission04', 'maps/gc_chemgeneral/gc_chemgeneral.map', 'mission05'),
   ('mission05', 'maps/gc_lasergeneral/gc_lasergeneral.map', 'mission06'),
   ('mission06', 'maps/gc_nukegeneral/gc_nukegeneral.map', 'mission07'),
   ('mission07', 'maps/gc_chinaboss/gc_chinaboss.map', None))),
 ('challenge_7',
  'China Infantry',
  (('mission01', 'maps/gc_airgeneral/gc_airgeneral.map', 'mission02'),
   ('mission02', 'maps/gc_stealth/gc_stealth.map', 'mission03'),
   ('mission03', 'maps/gc_tankgeneral/gc_tankgeneral.map', 'mission04'),
   ('mission04', 'maps/gc_superweaponsgeneral/gc_superweaponsgeneral.map', 'mission05'),
   ('mission05', 'maps/gc_nukegeneral/gc_nukegeneral.map', 'mission06'),
   ('mission06', 'maps/gc_lasergeneral/gc_lasergeneral.map', 'mission07'),
   ('mission07', 'maps/gc_chemgeneral/gc_chemgeneral.map', 'mission08'),
   ('mission08', 'maps/gc_chinaboss/gc_chinaboss.map', None))),
 ('challenge_8',
  'GLA Demolition',
  (('mission01', 'maps/gc_superweaponsgeneral/gc_superweaponsgeneral.map', 'mission02'),
   ('mission02', 'maps/gc_chemgeneral/gc_chemgeneral.map', 'mission03'),
   ('mission03', 'maps/gc_tankgeneral/gc_tankgeneral.map', 'mission04'),
   ('mission04', 'maps/gc_airgeneral/gc_airgeneral.map', 'mission05'),
   ('mission05', 'maps/gc_nukegeneral/gc_nukegeneral.map', 'mission06'),
   ('mission06', 'maps/gc_stealth/gc_stealth.map', 'mission07'),
   ('mission07', 'maps/gc_lasergeneral/gc_lasergeneral.map', 'mission08'),
   ('mission08', 'maps/gc_chinaboss/gc_chinaboss.map', None))))
CHALLENGE_NAMES = {campaign: name for campaign, name, _ in CHALLENGE_CAMPAIGNS}
CHALLENGE_MISSIONS = tuple(
    {"key": f"{campaign}_{number:02}",
     "name": f"Generals Challenge - {label} - Battle {number:02} - Victory",
     "campaign": campaign, "mission": mission, "map": map_name,
     "next_mission": next_mission, "id": BASE_ID + 0x200 + index * 16 + number}
    for index, (campaign, label, battles) in enumerate(CHALLENGE_CAMPAIGNS)
    for number, (mission, map_name, next_mission) in enumerate(battles, 1)
)
for mission in MISSIONS:
    number = int(mission["mission"][-2:])
    mission["next_mission"] = f"mission{number + 1:02}" if number < 5 else None
ALL_MISSIONS = MISSIONS + CHALLENGE_MISSIONS
BY_ID = {mission["id"]: mission for mission in ALL_MISSIONS}
BY_KEY = {mission["key"]: mission for mission in MISSIONS}
BY_CAMPAIGN_MISSION = {(m["campaign"], m["mission"]): m for m in MISSIONS}
# LOCATION_IDS remains the original protocol 1-3 set.
LOCATION_IDS = frozenset(m["id"] for m in MISSIONS)
ALL_LOCATION_IDS = frozenset(BY_ID)
ALL_BY_CAMPAIGN_MISSION = {(m["campaign"], m["mission"]): m for m in ALL_MISSIONS}
UNIT_ONLY_KEYS = frozenset({"usa_03", "gla_04"})

# Separate ranges preserve every released item and mission location ID.
MISSION_SETS = {
    key: {"key": key, "label": label, "item_id": BASE_ID + 0x400 + index,
          "item_name": label + (" Campaign Unlock" if index < 3 else " Generals Challenge Missions Unlock")}
    for index, (key, label) in enumerate(
        [(c.lower(), c) for c in CAMPAIGNS] + list(CHALLENGE_NAMES.items()))
}
SET_ITEMS = {s['item_id']: s['item_name'] for s in MISSION_SETS.values()}
ITEM_NAMES.update(SET_ITEMS)
SET_BONUSES = tuple(
    {"id": (BASE_ID + 0x500 + index * 8 + n if n <= 5
            else BASE_ID + 0x700 + index * 16 + n),
     "name": f"{s['label']} - Mission Set Complete - Bonus {n}", "campaign": key,
     "type": "set_bonus", "check_number": n}
    for index, (key, s) in enumerate(MISSION_SETS.items()) for n in range(1, 11)
)
MISSION_EXTRA_CHECKS = tuple(
    {**m, 'id': BASE_ID + 0x1000 + index * 16 + n,
     'name': f"{m['name']} - Check {n}", 'type': 'mission_extra',
     'mission_id': m['id'], 'check_number': n}
    for index, m in enumerate(ALL_MISSIONS) for n in range(2, 11)
)
ALL_CHECKS = ALL_MISSIONS + MISSION_EXTRA_CHECKS + SET_BONUSES
BY_ID.update({m['id']: m for m in ALL_CHECKS})
ALL_LOCATION_IDS = frozenset(BY_ID)


def selected_sets(missions):
    return [key for key in MISSION_SETS if any(m['campaign'] == key for m in missions)]


def with_set_bonuses(missions, mission_checks=1, set_checks=5):
    if (type(mission_checks) is not int or not 1 <= mission_checks <= 10
            or type(set_checks) is not int or not 0 <= set_checks <= 10):
        raise ValueError('Use 1-10 checks per mission and 0-10 checks per set.')
    missions = tuple(missions)
    keys = set(selected_sets(missions))
    ids = {m['id'] for m in missions}
    return (missions + tuple(m for m in MISSION_EXTRA_CHECKS
                             if m['mission_id'] in ids and m['check_number'] <= mission_checks)
            + tuple(m for m in SET_BONUSES if m['campaign'] in keys and m['check_number'] <= set_checks))


def earned_set_bonuses(missions, completed, set_checks=5):
    return {b['id'] for b in SET_BONUSES if b['check_number'] <= set_checks and
            any(m['campaign'] == b['campaign'] for m in missions) and
            all(m['id'] in completed for m in missions if m['campaign'] == b['campaign'])}


def choose_starting_sets(campaigns, challenge_count, explicit_labels, count, rng, required_challenges=()):
    by_label = {s['label']: key for key, s in MISSION_SETS.items()}
    if not set(explicit_labels) <= set(by_label):
        raise ValueError('Unknown starting mission set.')
    explicit = {by_label[label] for label in explicit_labels}
    if any(key not in CHALLENGE_NAMES and key not in {c.lower() for c in campaigns} for key in explicit):
        raise ValueError('A chosen starting story campaign must be enabled.')
    fixed_challenges = (explicit & set(CHALLENGE_NAMES)) | set(required_challenges)
    if len(fixed_challenges) > challenge_count:
        raise ValueError('Increase Generals Challenge campaign count to include chosen starting generals.')
    challenges = sorted(fixed_challenges | set(rng.sample(
        [key for key in CHALLENGE_NAMES if key not in fixed_challenges], challenge_count - len(fixed_challenges))))
    enabled = [key for key in MISSION_SETS if key in challenges or key in {c.lower() for c in campaigns}]
    if not enabled or not 1 <= count <= 12:
        raise ValueError('Enable a mission set and choose 1-12 starting sets.')
    count = min(count, len(enabled))
    if len(explicit) > count:
        raise ValueError('Starting set count is smaller than the number of specifically chosen sets.')
    starting = explicit | set(rng.sample([key for key in enabled if key not in explicit], count - len(explicit)))
    return challenges, [key for key in enabled if key in starting]


def select_missions(campaigns=CAMPAIGNS, disable_unit_only=False, challenges=()):
    if (len(set(campaigns)) != len(campaigns) or not set(campaigns) <= set(CAMPAIGNS)
            or len(set(challenges)) != len(challenges) or not set(challenges) <= set(CHALLENGE_NAMES)
            or type(disable_unit_only) is not bool):
        raise ValueError("Invalid campaign selection.")
    selected = tuple(m for m in MISSIONS if m["campaign"] in {c.lower() for c in campaigns}
                     and not (disable_unit_only and m["key"] in UNIT_ONLY_KEYS))
    selected += tuple(m for m in CHALLENGE_MISSIONS if m["campaign"] in challenges)
    if not selected:
        raise ValueError("Select at least one story campaign or one Generals Challenge campaign.")
    return selected

