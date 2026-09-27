"""CIA escort and Heroic loaded Humvee, created on the simulation thread."""

NAMES = 0x300
TEMPLATES = 0x390
VEHICLE = 0x39C
PASSENGER = 0x3A0
AGENT_COUNT, VEHICLE_COUNT, PASSENGER_COUNT, ATTEMPTS = 0x3A4, 0x3A8, 0x3AC, 0x3B0
RECIPE = ('AmericaVehicleHumvee', 'AmericaInfantryCIAOfficer', 'AmericaInfantryMissileDefender')
EXPERIENCE_OFFSET, CONTAIN_OFFSET, CONTAINED_BY_OFFSET = 0x18C, 0x170, 0x190
EXPERIENCE_TABLE_RVA, CONTAIN_TABLE_RVA = 0x553168, 0x555758
PROMOTE_RVA, VALID_CONTAINER_RVA, ADD_PASSENGER_RVA = 0x217A00, 0x226F70, 0x220720
NEW_OBJECT_RVA, SET_POSITION_RVA, DESTROY_RVA = 0xADB30, 0x1440A0, 0xA4000
SIGNATURES = ((PROMOTE_RVA, '53568bf18b5e0c57'),
              (VALID_CONTAINER_RVA, '5356578b7c241085'),
              (ADD_PASSENGER_RVA, '5356578b7c24108b'),
              (NEW_OBJECT_RVA, '568b74240885f657'),
              (SET_POSITION_RVA, '83ec70568bf18b46'),
              (DESTROY_RVA, '5156578bf98b4c24'))


def emit_reinforcements(e, j, labels, out, base, mailbox):
    from .consumables import (STRING, TEMPLATE, ANCHOR, POS, OFFSETS, FACTORY_RVA,
                             ASSISTANT_RVA, FIND_TEMPLATE_RVA, ASCII_CTOR_RVA,
                             ASCII_DTOR_RVA, ITERATE_RVA, LEGAL_RVA, BUILD_RVA)
    from .power import GAME_LOGIC_RVA

    def call(rva):
        e('b8', base + rva); e('ff d0')

    def promote(object_offset, failed):
        e('8b 87', object_offset); e('8b 88', EXPERIENCE_OFFSET)
        e('85 c9'); j('0f 84', failed)
        e('81 39', base + EXPERIENCE_TABLE_RVA); j('0f 85', failed)
        # setVeterancyLevel(LEVEL_HEROIC=3, provideFeedback=false) applies bonuses.
        e('6a 00 6a 03'); call(PROMOTE_RVA)
        e('8b 87', object_offset); e('8b 88', EXPERIENCE_OFFSET)
        e('83 79 0c 03'); j('0f 85', failed)

    def destroy(object_offset):
        e('ff b7', object_offset); e('8b 0d', base + GAME_LOGIC_RVA); call(DESTROY_RVA)

    labels['reinforcements'] = len(out)
    for offset in (24, VEHICLE, PASSENGER, AGENT_COUNT, VEHICLE_COUNT, PASSENGER_COUNT):
        e('c7 87', offset, 0)
    e('83 be 60 01 00 00 00'); j('0f 84', 'reject')  # local player's default team
    e('83 3d', base + FACTORY_RVA); e('00'); j('0f 84', 'reject')
    # Resolve the complete recipe before creating anything. Own/destroy each string.
    for index in range(3):
        e('68', mailbox + NAMES + index * 48); e('b9', mailbox + STRING); call(ASCII_CTOR_RVA)
        e('6a 00 68', mailbox + STRING); e('8b 0d', base + FACTORY_RVA); call(FIND_TEMPLATE_RVA)
        e('89 87', TEMPLATES + index * 4)
        e('b9', mailbox + STRING); call(ASCII_DTOR_RVA)
        e('83 bf', TEMPLATES + index * 4); e('00'); j('0f 84', 'reject')
    e('c7 87', ANCHOR, 0); e('c7 87', ANCHOR + 4, 0)
    e('68', mailbox + ANCHOR)
    e('e8 00 00 00 00 58 05')
    labels['_anchor_fix'] = len(out); e('00 00 00 00')
    e('50 89 f1'); call(ITERATE_RVA)
    e('83 bf', ANCHOR); e('00'); j('0f 84', 'reject')
    e('31 db')  # EBX: unit stage 0=Humvee, 1..3=CIA. ESI=local player.
    labels['rf_unit'] = len(out)
    e('31 ed')  # EBP: bounded placement candidate, reset for each ground unit.
    e('8b 87', TEMPLATES); e('85 db'); j('0f 84', 'rf_template')
    e('8b 87', TEMPLATES + 4)
    labels['rf_template'] = len(out)
    e('89 87', TEMPLATE)
    labels['rf_spot'] = len(out)
    e('8b 87', ANCHOR)
    e('d9 40 38 d8 84 ef', OFFSETS); e('d9 9f', POS)
    e('d9 40 3c d8 84 ef', OFFSETS + 4); e('d9 9f', POS + 4)
    e('8b 50 40 89 97', POS + 8)
    e('56 50 6a 17 6a 00 ff b7', TEMPLATE); e('68', mailbox + POS)
    e('8b 0d', base + ASSISTANT_RVA); call(LEGAL_RVA)
    e('85 c0'); j('0f 85', 'rf_next_spot')
    e('56 6a 00 68', mailbox + POS); e('ff b7', TEMPLATE); e('6a 00')
    e('8b 0d', base + ASSISTANT_RVA); call(BUILD_RVA)
    e('85 c0'); j('0f 84', 'rf_next_spot')
    e('85 db'); j('0f 84', 'rf_vehicle')
    e('ff 87', AGENT_COUNT); e('ff 47 18'); j('e9', 'rf_next_unit')

    labels['rf_vehicle'] = len(out)
    e('89 87', VEHICLE)
    promote(VEHICLE, 'rf_bad_vehicle')
    e('8b 87', VEHICLE); e('8b 88', CONTAIN_OFFSET)
    e('85 c9'); j('0f 84', 'rf_bad_vehicle')
    e('81 39', base + CONTAIN_TABLE_RVA); j('0f 85', 'rf_bad_vehicle')
    e('39 41 ec'); j('0f 85', 'rf_bad_vehicle')  # contain interface belongs to our new Humvee
    e('ff 87', VEHICLE_COUNT); e('ff 47 18'); e('c7 87', ATTEMPTS, 0)
    labels['rf_passenger'] = len(out)
    # Factory creation uses the same local team. Passengers are loaded immediately,
    # using native validation/events/world removal, never raw container field edits.
    e('6a 00 6a 00 ff b6 60 01 00 00 ff b7', TEMPLATES + 8)
    e('8b 0d', base + FACTORY_RVA); call(NEW_OBJECT_RVA)
    e('89 87', PASSENGER); e('85 c0'); j('0f 84', 'rf_next_passenger')
    e('8b c8 68', mailbox + POS); call(SET_POSITION_RVA)
    promote(PASSENGER, 'rf_bad_passenger')
    e('8b 87', VEHICLE); e('8b 88', CONTAIN_OFFSET)
    e('6a 01 ff b7', PASSENGER); call(VALID_CONTAINER_RVA)
    e('84 c0'); j('0f 84', 'rf_bad_passenger')
    e('8b 87', VEHICLE); e('8b 88', CONTAIN_OFFSET)
    e('ff b7', PASSENGER); call(ADD_PASSENGER_RVA)
    e('8b 87', PASSENGER); e('8b 80', CONTAINED_BY_OFFSET)
    e('3b 87', VEHICLE); j('0f 85', 'rf_bad_passenger')
    e('ff 87', PASSENGER_COUNT); e('ff 47 18'); j('e9', 'rf_next_passenger')
    labels['rf_bad_passenger'] = len(out)
    destroy(PASSENGER)
    labels['rf_next_passenger'] = len(out)
    e('ff 87', ATTEMPTS); e('83 bf', ATTEMPTS); e('05'); j('0f 82', 'rf_passenger')
    j('e9', 'rf_next_unit')
    labels['rf_bad_vehicle'] = len(out)
    destroy(VEHICLE)
    j('e9', 'rf_next_unit')

    labels['rf_next_spot'] = len(out)
    e('45 83 fd 18'); j('0f 82', 'rf_spot')
    labels['rf_next_unit'] = len(out)
    e('43 83 fb 04'); j('0f 82', 'rf_unit')
    e('c7 07', 2); j('e9', 'done')
