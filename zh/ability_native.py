"""Simulation-thread abilities using stock vision, repair markers and air drops."""
import math
import struct

from .memory import MemoryReadError

TARGET, RADIUS, LIFETIME, OBJECT, OCL, EDGE = 0x180, 0x18C, 0x190, 0x194, 0x198, 0x1A0
OCL_NAME = 0x140
PARTITION_RVA, TERRAIN_RVA, OCL_STORE_RVA = 0x63A078, 0x639594, 0x639B64
NEW_OBJECT, SET_POSITION, SET_RANGE = 0xADB30, 0x1440A0, 0x14DF30
DELETE_KEY, FIND_MODULE, SET_LIFETIME = 0x244190, 0x149F90, 0x244220
DESTROY, FIND_OCL, CREATE_OCL, CLOSEST_EDGE = 0xA4000, 0xBE220, 0xBDEF0, 0x4B270
DROP_CLONE, DROP_LIST, DROP_POINTER = 0x400, 0x4B0, 0x4BC
DROP_PAYLOAD, DROP_TEMPLATE, DROP_FLAGS, DROP_STRING, DROP_RESULT = 0x4C0, 0x4C8, 0x4CC, 0x4D0, 0x4D4
DROP_NAME, CHUTE_NAME = 0x500, 0x530
DROP_SLOTS, DROP_COUNT, DROP_NODE, DROP_CHUTE = 0x4D8, 0x4DC, 0x4E0, 0x4E4
DROP_DEST, DROP_SPACING = 0x550, 0x55C
TRANSPORT_SLOTS = 0x231
FINAL_OVERRIDE, OBJECT_TEMPLATE = 0x22340, 0x143D10
CHUTE_VTABLE, CHUTE_DESTINATION = 0x556B50, 0x22CA60
# Final DeliverPayloadNugget table, assigned at Steam VA 0x4BABB5.
# 0x5484AC is ObjectCreationNugget's BASE table, used only during construction.
DELIVER_VTABLE = 0x548570
# Steam KindOfNames[40], also used by ParachuteContain at VA 0x62BB71.
PARACHUTABLE_MASK = 1 << (40 - 32)
STAGE, DETAIL = 0x1B0, 0x1B4
STAGES = {0: 'mission validation', 1: 'local team/factory', 2: 'stock paradrop/strike lookup',
          3: 'terrain edge', 4: 'ability template', 5: 'ability object creation',
          6: 'vision lifetime module', 7: 'paradrop recipe shape',
          8: 'paradrop object type', 9: 'Patriot ability definition lookup (restart Zero Hour after asset installation)',
          10: 'Patriot structure flags', 11: 'plane/payload creation',
          12: 'loaded Patriot cargo validation'}


def rejection_detail(game, mailbox):
    stage = game.pointer(mailbox + STAGE)
    message = STAGES.get(stage, f'native stage {stage}')
    if stage == 8:
        message += f" (observed type {game.pointer(mailbox + DETAIL):#x}, expected {game.base + DELIVER_VTABLE:#x})"
    return message


def map_bounds(game):
    partition = game.pointer(game.base + PARTITION_RVA)
    if not partition or game.pointer(partition) != game.base + 0x54EA58:
        raise MemoryReadError('Ability map bounds are unavailable.')
    bounds = struct.unpack('<6f', game.read(partition + 0x10, 24))
    if (not all(math.isfinite(v) for v in bounds)
            or not all(0 < bounds[i + 3] - bounds[i] < 100000 for i in (0, 1))):
        raise MemoryReadError('Invalid ability map bounds.')
    return bounds


def emit_ability(e, j, labels, out, base, mailbox):
    """ESI=validated local Player, EDI=mailbox. All calls use native thiscall."""
    from .consumables import FACTORY_RVA, ASCII_CTOR_RVA, ASCII_DTOR_RVA, FIND_TEMPLATE_RVA, STRING, TEMPLATE
    def call(rva):
        e('b8', base + rva); e('ff d0')
    def stage(number):
        e('c7 87', STAGE, number)
    labels['ability'] = len(out)
    stage(1)
    # A vanished factory/team or a mission transition cannot create foreign objects.
    e('83 be 60 01 00 00 00'); j('0f 84', 'reject')
    e('a1', base + FACTORY_RVA); e('85 c0'); j('0f 84', 'reject')
    e('83 7f 1c 03'); j('0f 84', 'ability_template')
    e('83 7f 1c 07'); j('0f 84', 'ability_template')
    stage(2)
    e('8b 0d', base + OCL_STORE_RVA); e('85 c9'); j('0f 84', 'reject')
    e('68', mailbox + OCL_NAME); call(FIND_OCL)
    e('89 87', OCL); e('85 c0'); j('0f 84', 'reject')
    stage(3)
    e('8b 0d', base + TERRAIN_RVA); e('85 c9'); j('0f 84', 'reject')
    e('68', mailbox + TARGET); e('68', mailbox + EDGE); call(CLOSEST_EDGE)
    labels['ability_template'] = len(out)
    stage(4)
    e('68', mailbox + 32); e('b9', mailbox + STRING); call(ASCII_CTOR_RVA)
    e('6a 00 68', mailbox + STRING); e('8b 0d', base + FACTORY_RVA); call(FIND_TEMPLATE_RVA)
    e('89 87', TEMPLATE); e('b9', mailbox + STRING); call(ASCII_DTOR_RVA)
    e('83 bf', TEMPLATE); e('00'); j('0f 84', 'reject')
    stage(5)
    e('6a 00 6a 00 ff b6 60 01 00 00 ff b7', TEMPLATE)
    e('8b 0d', base + FACTORY_RVA); call(NEW_OBJECT)
    e('89 87', OBJECT); e('85 c0'); j('0f 84', 'reject')
    # Position the stock single-burst repair marker before simulation resumes.
    # Its own AutoHeal/Deletion updates perform the burst and remove it; it
    # needs no vision range, lifetime extension, Command Center or science.
    e('83 7f 1c 07'); j('0f 84', 'repair_position')
    stage(6)
    call(DELETE_KEY); e('50 8b 8f', OBJECT); call(FIND_MODULE)
    e('85 c0'); j('0f 84', 'ability_cleanup')
    e('8b c8 ff b7', LIFETIME); e('ff b7', LIFETIME); call(SET_LIFETIME)
    e('68', mailbox + TARGET); e('8b 8f', OBJECT); call(SET_POSITION)
    e('ff b7', RADIUS); e('8b 8f', OBJECT); call(SET_RANGE)
    e('83 7f 1c 03'); j('0f 84', 'ability_success')
    e('83 7f 1c 06'); j('0f 84', 'patriot_drop')
    e('6a 00 6a 00 68', mailbox + TARGET); e('68', mailbox + EDGE)
    e('ff b7', OBJECT); e('8b 8f', OCL); call(CREATE_OCL)
    e('85 c0'); j('0f 85', 'ability_success')
    # OCL can fail after a partial creation. Keep the cooldown in that uncertain
    # case; the vision object still expires through its native lifetime module.
    e('c7 07', 5); j('e9', 'done')
    labels['repair_position'] = len(out)
    e('68', mailbox + TARGET); e('8b 8f', OBJECT); call(SET_POSITION)
    labels['ability_success'] = len(out)
    e('c7 07', 2); j('e9', 'done')
    labels['ability_cleanup'] = len(out)
    e('ff b7', OBJECT); e('8b 0d', base + 0x639B0C); call(DESTROY)
    j('e9', 'reject')
    labels['patriot_drop'] = len(out)
    stage(7)
    # Private copy of the stock paradrop's sole DeliverPayload nugget. Never
    # change the global OCL: ordinary Ranger paradrops must remain untouched.
    e('8b 87', OCL); e('8b 10 85 d2'); j('0f 84', 'ability_cleanup')
    e('8d 4a 04 3b 48 04'); j('0f 85', 'ability_cleanup')
    e('8b 02 85 c0'); j('0f 84', 'ability_cleanup')
    stage(8)
    e('8b 10 89 97', DETAIL)
    e('81 38', base + DELIVER_VTABLE); j('0f 85', 'ability_cleanup')
    e('56 57 8b f0 bf', mailbox + DROP_CLONE); e('b9', 44); e('fc f3 a5 5f 5e')
    stage(9)
    e('68', mailbox + DROP_NAME); e('b9', mailbox + DROP_STRING); call(ASCII_CTOR_RVA)
    e('6a 00 68', mailbox + DROP_STRING); e('8b 0d', base + FACTORY_RVA); call(FIND_TEMPLATE_RVA)
    e('89 87', DROP_TEMPLATE); e('b9', mailbox + DROP_STRING); call(ASCII_DTOR_RVA)
    e('8b 87', DROP_TEMPLATE); e('85 c0'); j('0f 84', 'ability_cleanup')
    # KindOf and transport slots are read from the final map override.
    e('89 c1'); call(FINAL_OVERRIDE); e('89 87', DROP_TEMPLATE)
    # Reject a wrong template layout before touching flags or creating payloads.
    stage(10)
    e('f6 40 68 80'); j('0f 84', 'ability_cleanup')  # KINDOF_STRUCTURE
    e('8b 50 6c 89 97', DROP_FLAGS)
    e('0f b6 90', TRANSPORT_SLOTS); e('89 97', DROP_SLOTS)
    e('68', mailbox + DROP_NAME); e('b9', mailbox + DROP_PAYLOAD); call(ASCII_CTOR_RVA)
    e('68', mailbox + CHUTE_NAME); e('b9', mailbox + DROP_CLONE + 8); call(ASCII_CTOR_RVA)
    for offset, value in ((DROP_PAYLOAD + 4, 3), (DROP_CLONE + 0xC, mailbox + DROP_PAYLOAD),
                          (DROP_CLONE + 0x10, mailbox + DROP_PAYLOAD + 8),
                          (DROP_CLONE + 0x14, mailbox + DROP_PAYLOAD + 8),
                          (DROP_CLONE + 0x60, 5), (DROP_POINTER, mailbox + DROP_CLONE),
                          (DROP_LIST, mailbox + DROP_POINTER), (DROP_LIST + 4, mailbox + DROP_POINTER + 4),
                          (DROP_LIST + 8, mailbox + DROP_POINTER + 4)):
        e('c7 87', offset, value)
    e('c6 87', DROP_CLONE + 0x7D); e('00')  # spread drops along the flight path
    # Container admission requires PARACHUTABLE. All payloads are constructed
    # synchronously here; restore the stock template before the simulation resumes.
    stage(11)
    e('8b 87', DROP_TEMPLATE); e('81 48 6c', PARACHUTABLE_MASK)
    # TransportContain unwraps the parachute and rejects a slotless building,
    # even though ParachuteContain itself accepts PARACHUTABLE structures.
    e('c6 80', TRANSPORT_SLOTS); e('01')
    e('c7 87', DROP_COUNT, 0)
    e('6a 00 6a 00 68', mailbox + TARGET); e('68', mailbox + EDGE)
    e('ff b7', OBJECT); e('b9', mailbox + DROP_LIST); call(CREATE_OCL)
    e('89 87', DROP_RESULT)
    e('8b 87', DROP_TEMPLATE); e('8b 97', DROP_FLAGS); e('89 50 6c')
    e('8b 97', DROP_SLOTS); e('88 90', TRANSPORT_SLOTS)
    for offset in (DROP_PAYLOAD, DROP_CLONE + 8):
        e('b9', mailbox + offset); call(ASCII_DTOR_RVA)
    # A non-null plane alone does not prove payload creation/loading succeeded.
    # Inspect its three parachutes and each actual rider, then give the chutes
    # distinct landing destinations. Native ParachuteDirectly remains off so
    # the delivery AI does not replace them with one shared destination.
    stage(12)
    e('8b 87', DROP_RESULT); e('85 c0'); j('0f 84', 'drop_uncertain')
    e('8b 88 70 01 00 00 85 c9'); j('0f 84', 'drop_uncertain')
    e('51 8b 01 ff 90 a4 00 00 00 59 83 f8 03'); j('0f 85', 'drop_uncertain')
    e('8b 01 ff 90 a8 00 00 00 85 c0'); j('0f 84', 'drop_uncertain')
    e('8b 00 8b 00 89 87', DROP_NODE)
    labels['drop_validate'] = len(out)
    e('8b 87', DROP_NODE); e('8b 48 08 85 c9'); j('0f 84', 'drop_uncertain')
    e('8b 89 70 01 00 00 85 c9'); j('0f 84', 'drop_uncertain')
    e('81 39', base + CHUTE_VTABLE); j('0f 85', 'drop_uncertain')
    e('89 8f', DROP_CHUTE)
    e('8b 01 ff 90 a8 00 00 00 85 c0'); j('0f 84', 'drop_uncertain')
    e('8b 00 8b 00 8b 48 08 85 c9'); j('0f 84', 'drop_uncertain')
    call(OBJECT_TEMPLATE)
    e('3b 87', DROP_TEMPLATE); j('0f 85', 'drop_uncertain')
    # Three pads, 70 world units apart, centered on the clicked point.
    e('8b 87', DROP_COUNT)
    e('d9 87', TARGET); e('d8 84 87', DROP_SPACING); e('d9 9f', DROP_DEST)
    for axis in (4, 8):
        e('8b 87', TARGET + axis); e('89 87', DROP_DEST + axis)
    e('68', mailbox + DROP_DEST); e('8b 8f', DROP_CHUTE); call(CHUTE_DESTINATION)
    e('ff 87', DROP_COUNT)
    e('8b 87', DROP_NODE); e('8b 00 89 87', DROP_NODE)
    e('83 bf', DROP_COUNT); e('03'); j('0f 82', 'drop_validate')
    j('e9', 'ability_success')
    labels['drop_uncertain'] = len(out)
    e('c7 07', 5); j('e9', 'done')
