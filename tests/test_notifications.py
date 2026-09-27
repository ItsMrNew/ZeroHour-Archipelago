import asyncio
import ast
from collections import namedtuple
import json
from pathlib import Path
import struct
import typing
from types import MethodType
from types import SimpleNamespace

import pytest

from test_check_counts import configurable_packet
from test_client import Socket
from test_unlock_menu import MenuSimulation
from zh.client import ZeroHourClient
from zh.notifications import ItemNotifications, DEFAULT_NOTIFICATIONS, validate_settings
from zh.state import Progress
from zh.unlock_menu import ROW_DEFS, ROWS, STRIDE, TOAST_ROWS


def event(sender=1, recipient=2, item=10, location=100, kind='ItemSend'):
    return {'cmd':'PrintJSON', 'type':kind, 'receiving':recipient,
            'item':{'player':sender, 'item':item, 'location':location, 'flags':0}}


def connection():
    return {'team':0, 'slot':1,
        'players':[{'team':0, 'slot':1, 'alias':'You'}, {'team':0, 'slot':2, 'alias':'Friend'}],
        'slot_info':{'1':{'game':'Zero', 'name':'One'}, '2':{'game':'Other', 'name':'Two'},
                     '3':{'game':'Other', 'name':'Three'},
                     '4':{'game':'Zero', 'name':'Group', 'group_members':[1,5]}}}


def test_filtering_metadata_duplicates_and_group_deliveries():
    n=ItemNotifications()
    assert n.connected(connection(), DEFAULT_NOTIFICATIONS)==['Other','Zero']
    n.data_package({'data':{'games':{'Other':{'item_name_to_id':{'Magic Sword':10}},
                                    'Zero':{'item_name_to_id':{'Power':10}}}}})
    n.receive(event(2,3)); assert not n.queue
    n.receive(event()); n.receive(event())
    assert len(n.queue)==1
    assert n.lines()==['You sent','Magic Sword','to Friend','','','']
    n.configure({'scope':'all','seconds':8})
    n.receive(event(2,3,location=101))
    assert n.lines()[3:] == ['Friend sent','Magic Sword','to Three']
    n.configure(DEFAULT_NOTIFICATIONS)
    assert n.lines()[3:]==['','','']  # Remove other players immediately.
    n.receive(event(2,4,location=102))
    assert n.lines()[3:]==['Friend sent','Power','to Group']
    n.configure({'scope':'off','seconds':8})
    n.receive(event(location=103)); assert n.lines()==['']*6 and not n.queue


def test_realtime_duration_queue_and_cheat_repeats():
    now=[0.0]; n=ItemNotifications(clock=lambda:now[0])
    n.connected(connection(), DEFAULT_NOTIFICATIONS)
    for i in range(3): n.receive(event(location=-1, kind='ItemCheat'))
    assert len(n.queue)==3
    assert n.lines()[0] and len(n.queue)==1
    now[0]=7.9; assert n.lines()[3]
    now[0]=8; assert n.lines()[0] and not n.lines()[3] and not n.queue
    n.configure({'scope':'you','seconds':2})
    now[0]=10; assert n.lines()==['']*6
    assert n.selection(75)['seconds']==1
    n.configure({'scope':'you','seconds':60}); assert n.selection(76)['seconds']==60
    n.receive({**event(), 'team':1}); assert not n.queue
    n.receive({'type':'Hint'}); assert not n.queue
    for value in ({}, None, {**DEFAULT_NOTIFICATIONS,'seconds':True}):
        with pytest.raises(ValueError): validate_settings(value)


def test_protocol_requests_names_and_preferences_survive_reconnect(tmp_path, monkeypatch):
    async def run():
        c=ZeroHourClient('localhost:1','test',state_dir=tmp_path); sock=Socket()
        await c.handle(sock, {'cmd':'RoomInfo','seed_name':'notifications'})
        packet=configurable_packet(); packet.update(connection())
        await c.handle(sock,packet)
        assert {'cmd':'GetDataPackage','games':['Other','Zero']} in sock.packets
        await c.handle(sock,{'cmd':'DataPackage','data':{'games':{'Other':{'item_name_to_id':{'Magic Sword':10}}}}})
        await c.handle(sock,event()); assert c.notifications.lines()[1]=='Magic Sword'
        c.notification_event(72); c.notification_event(76)
        assert c.progress.notification_settings=={'scope':'all','seconds':9}
        await c.handle(sock,packet)
        await c.handle(sock,event()); assert len(c.notifications.active)==1 and not c.notifications.queue
        loaded=Progress(tmp_path,*c.identity,location_ids=c.location_ids)
        assert loaded.notification_settings==c.notifications.settings
        assert Progress(tmp_path,'other',0,1).notification_settings==DEFAULT_NOTIFICATIONS
        # Inventory synchronization is never used as a source of toast messages.
        await c.handle(sock,{'cmd':'ReceivedItems','index':0,'items':[]})
        assert not c.notifications.queue
        c.notification_event(73); assert c.notifications.lines()==['']*6
    asyncio.run(run())


@pytest.mark.parametrize('outside', ['main_menu','paused','intro','loading'])
def test_native_toasts_visible_outside_play_and_cannot_enable_actions(outside):
    sim=MenuSimulation()
    if outside=='main_menu': sim.put(sim.logic+0x94,2)
    elif outside=='paused': sim.u.mem_write(sim.logic+0x64,b'\1')
    elif outside=='intro': sim.u.mem_write(sim.ui+13,b'\0')
    else: sim.u.mem_write(sim.logic+0x51,b'\1')
    # Start on the main menu, before any mission has created our windows.
    for ident in range(80,86):
        index=next(i for i,row in enumerate(ROW_DEFS) if row[0]==ident)
        sim.put(sim.mailbox+ROWS+index*STRIDE+28,0)
    sim.tick()
    assert not sim.get(sim.window(1)+4)&16  # read-only tracker remains available
    for ident in range(80,86):
        assert sim.windows[sim.window(ident)]['parent']==0
        assert not sim.get(sim.window(ident)+4)&(16|8)  # visible, disabled/noninteractive
    sim.click(32)
    assert sim.get(sim.mailbox+12)==0
    sim.put(sim.mailbox,2); sim.tick()
    assert all(sim.window(ident) in sim.destroyed for ident in range(80,86))


def test_native_notification_tab_buttons_and_toast_recreation():
    sim=MenuSimulation(); sim.tick(); sim.click(1); sim.click(8); sim.tick()
    assert sim.get(sim.mailbox+20)==4
    assert not sim.get(sim.window(71)+4)&16
    assert sim.get(sim.window(51)+4)&16
    for ident in (71,72,73,75,76):
        sim.put(sim.mailbox+12,0); sim.click(ident); assert sim.get(sim.mailbox+12)==ident
    old=sim.get(sim.mailbox+TOAST_ROWS[0])
    sim.run(sim.windows[old]['callback'], (old,2,0,0))
    assert sim.get(sim.mailbox+TOAST_ROWS[0])==0
    sim.tick(); assert sim.get(sim.mailbox+TOAST_ROWS[0]) not in (0,old)


def server_send_packet(count=1):
    """Execute the real AP 0.6.7 send command and text broadcaster in a fake room."""
    from zh.mission_data import GAME, CASH_ITEM_ID
    source = Path('.research/Archipelago-0.6.7/MultiServer.py')
    if not source.exists():
        pytest.skip('Archipelago source checkout unavailable')
    tree = ast.parse(source.read_text(encoding='utf-8-sig'))
    wanted = {'_cmd_send', '_cmd_send_multiple', 'broadcast_text_all'}
    nodes = [node for cls in tree.body if isinstance(cls, ast.ClassDef)
             for node in cls.body if isinstance(node, ast.FunctionDef) and node.name in wanted]
    assert {n.name for n in nodes} == wanted
    for node in nodes:
        node.decorator_list = []
    packets, deliveries = [], []
    namespace = dict(typing=typing, NetworkItem=namedtuple('NetworkItem','item location player'),
                     get_intended_text=lambda name, choices: (name, True, ''),
                     send_new_items=lambda ctx: None,
                     send_items_to=lambda ctx, team, slot, *items: deliveries.extend(items))
    exec(compile(ast.Module(body=nodes, type_ignores=[]), str(source), 'exec'), namespace)
    ctx = SimpleNamespace(logger=SimpleNamespace(info=lambda *args: None),
                          broadcast_all=packets.extend, player_names={(0,1):'You'},
                          player_name_lookup={'You':(0,1)}, games={1:GAME},
                          item_names_for_game=lambda game: {'Progressive Starting Cash':CASH_ITEM_ID},
                          get_aliased_name=lambda team, slot: 'You')
    ctx.broadcast_text_all = MethodType(namespace['broadcast_text_all'],ctx)
    command = SimpleNamespace(ctx=ctx, output=lambda *args: None)
    command._cmd_send_multiple = MethodType(namespace['_cmd_send_multiple'],command)
    if count == 1:
        assert namespace['_cmd_send'](command, 'You', 'Progressive', 'Starting', 'Cash')
    else:
        assert command._cmd_send_multiple(count, 'You', 'Progressive', 'Starting', 'Cash')
    assert len(deliveries) == count
    return json.loads(json.dumps(packets[0]))


@pytest.mark.parametrize('outside', ['playing', 'main_menu', 'paused'])
@pytest.mark.parametrize('command', ['getitem', 'send', 'send_multiple'])
def test_cheat_notification_text_reaches_native_gadget(tmp_path, outside, command):
    from zh.mission_data import GAME, CASH_ITEM_ID
    async def run():
        client = ZeroHourClient('localhost:1','test',state_dir=tmp_path)
        socket = Socket()
        await client.handle(socket, {'cmd':'RoomInfo','seed_name':'cheat-toast'})
        packet = configurable_packet()
        packet.update(team=0, slot=1, players=[{'team':0,'slot':1,'alias':'You'}],
                      slot_info={'1':{'game':GAME, 'name':'You'}})
        await client.handle(socket, packet)
        notice = ({**event(1,1,CASH_ITEM_ID,-1,'ItemCheat'), 'team':0,
                   'data':[{'text':'Cheat console: sending cash'}]} if command == 'getitem'
                  else server_send_packet(3 if command == 'send_multiple' else 1))
        await client.handle(socket, notice)
        sim = MenuSimulation()
        if outside == 'main_menu': sim.put(sim.logic+0x94, 2)
        elif outside == 'paused': sim.u.mem_write(sim.logic+0x64, b'\1')
        for ident, (text, flags) in client.notifications.labels().items():
            index = next(i for i,row in enumerate(ROW_DEFS) if row[0] == ident)
            sim.u.mem_write(sim.mailbox+ROWS+index*STRIDE+28,
                            struct.pack('<I', flags)+text.encode().ljust(64,b'\0'))
        sim.tick()
        assert sim.texts[sim.window(80)] == ('You sent' if command=='getitem' else 'Server sent')
        assert sim.texts[sim.window(81)] == 'Progressive Starting Cash' + (' x3' if command=='send_multiple' else '')
        assert not sim.get(sim.window(81)+4)&16
        assert sim.texts[sim.window(82)] == 'to You'
        assert sim.get(sim.window(81)+0x190) == 0xFF6D8BE8
        await client.handle(socket, notice)
        assert len(client.notifications.queue) == 1
        # Inventory replay does not duplicate the live notice.
        await client.handle(socket, {'cmd':'ReceivedItems','index':0,'items':[
            {'item':CASH_ITEM_ID,'location':-1,'player':0,'flags':0}]})
        assert len(client.notifications.queue) == 1
    asyncio.run(run())


def test_server_send_filters_aliases_and_rejects_unrelated_text():
    n = ItemNotifications()
    n.connected(connection(), DEFAULT_NOTIFICATIONS)
    def notice(recipient='Two', item='Magic Sword', count=''):
        return {'cmd':'PrintJSON','data':[{'text':f'Cheat console: sending {count}"{item}" to {recipient}'}]}
    n.receive(notice()); assert not n.queue  # Yours only excludes other recipients.
    n.configure({'scope':'all','seconds':8})
    n.receive(notice('Friend (Two)')); assert n.lines()[:2] == ['Server sent','Magic Sword']
    n.configure({'scope':'you','seconds':8})
    n.receive(notice('You (One)')); assert n.lines()[:2] == ['Server sent','Magic Sword']
    n.configure({'scope':'off','seconds':8}); n.receive(notice('One')); assert not n.queue
    n.configure({'scope':'all','seconds':8})
    for invalid in (notice('Missing'), notice(count='0 of '), notice(count='101 of '),
                    {**notice(), 'type':'Chat'}, {**notice(), 'team':1},
                    {'cmd':'PrintJSON','data':[{'text':'Friend: Cheat console: sending "X" to Two'}]}):
        n.receive(invalid)
        assert not n.queue


@pytest.mark.parametrize('flags,colour', [(0,0xFF00EEEE), (1,0xFFAF99EF),
    (2,0xFF6D8BE8), (4,0xFFFA8072), (3,0xFFAF99EF), (6,0xFF6D8BE8)])
def test_other_world_item_flags_colour_only_the_item(flags, colour):
    n = ItemNotifications()
    n.connected(connection(), DEFAULT_NOTIFICATIONS)
    n.data_package({'data':{'games':{'Other':{'item_name_to_id':{'Magic Sword':10}}}}})
    packet = event(); packet['item']['flags'] = flags
    n.receive(packet)
    sim = MenuSimulation()
    labels = n.labels()
    assert ' '.join(labels[i][0] for i in (80,81,82)) == 'You sent Magic Sword to Friend'
    for index, row in enumerate(ROW_DEFS):
        if row[0] in labels:
            text, style = labels[row[0]]
            sim.u.mem_write(sim.mailbox+ROWS+index*STRIDE+28,
                            struct.pack('<I',style)+text.encode().ljust(64,b'\0'))
    sim.tick()
    for offset in (0x188,0x190,0x198):
        assert sim.get(sim.window(81)+offset) == colour
    for ident in (80,82):
        assert sim.get(sim.window(ident)+0x190) == 0xFFF3F6F8
    for ident in (80,81,82):
        assert sim.windows[sim.window(ident)]['font'] == sim.manager+0x1F100
        assert sim.get(sim.window(ident)+0xB4) == 0xFF101820
        assert not sim.get(sim.window(ident)+4)&(8|16)
    assert all(sim.get(sim.window(i)+4)&16 for i in (83,84,85))


@pytest.mark.parametrize('outside', ['playing','main_menu','paused'])
def test_native_cards_anchor_to_right_edge_and_follow_resolution_without_new_item(outside):
    sim = MenuSimulation()
    view = sim.manager+0x1E000
    sim.put(sim.base+0x639598,view)
    sim.put(view,sim.base+0x568B58)
    if outside == 'main_menu': sim.put(sim.logic+0x94,2)
    elif outside == 'paused': sim.u.mem_write(sim.logic+0x64,b'\1')
    for width, origin in ((1920,0),(800,0),(2560,40)):
        sim.put(view+0x18,width); sim.put(view+0x20,origin)
        sim.tick()
        for ident in range(80,86):
            window = sim.window(ident)
            assert sim.get(window+0x10) == width+origin-12-360
            assert sim.get(window+0x18) == width+origin-12
            assert sim.get(window+0x14) == 12+(ident-80)//3*62+(ident-80)%3*18
            assert sim.get(window+8) == 360
        assert sim.get(sim.mailbox+32) == 0


def test_server_cheat_classification_matches_world_for_every_local_item():
    from enum import IntFlag
    from zh import mission_data
    from zh.notifications import local_item_flags
    class ItemClassification(IntFlag):
        filler=0; progression=1; useful=2; trap=4
    source = Path('worlds/generals_zh/__init__.py')
    tree = ast.parse(source.read_text(encoding='utf-8-sig'))
    method = next(node for cls in tree.body if isinstance(cls,ast.ClassDef)
                  for node in cls.body if isinstance(node,ast.FunctionDef) and node.name=='create_item')
    namespace = {**vars(mission_data),'ItemClassification':ItemClassification,
                 'ZeroHourItem':lambda name,flags,code,player: int(flags)}
    exec(compile(ast.Module(body=[method],type_ignores=[]),str(source),'exec'),namespace)
    world = SimpleNamespace(item_name_to_id={v:k for k,v in mission_data.ITEM_NAMES.items()},player=1)
    for code, name in mission_data.ITEM_NAMES.items():
        assert local_item_flags(name) == local_item_flags(code) == namespace['create_item'](world,name)


@pytest.mark.parametrize('item_name', ['Mission Report','Supply Drop','Reinforcements'])
def test_local_filler_colours_correct_old_room_flags_and_cheats(item_name):
    from zh.mission_data import GAME, ITEM_NAMES
    code = next(code for code,name in ITEM_NAMES.items() if name == item_name)
    n = ItemNotifications()
    packet = connection(); packet['slot_info']['1']['game'] = GAME
    n.connected(packet,DEFAULT_NOTIFICATIONS)
    for kind in ('ItemSend','ItemCheat'):
        packet = event(2,1,code,-1,kind); packet['item']['flags'] = 2
        result = n.receive(packet)
        assert n.log_parts(result)[1] == (item_name,'#00EEEE')
    result = n.receive({'cmd':'PrintJSON','data':[{'text':f'Cheat console: sending "{item_name}" to One'}]})
    assert n.log_parts(result)[1] == (item_name,'#00EEEE')
    assert n.labels()[81][1] & 1024
    # Same numeric ID in another game must retain that game's classification.
    packet = event(1,2,code,-1); packet['item']['flags'] = 2
    assert n.receive(packet)[4] == 2


def test_client_transfers_carry_item_colours_without_duplicate_inventory_logs(tmp_path, caplog):
    from zh.mission_data import GAME, SUPPLY_DROP_ID
    async def run():
        client=ZeroHourClient('localhost:1','test',state_dir=tmp_path)
        socket=Socket()
        await client.handle(socket,{'cmd':'RoomInfo','seed_name':'coloured-logs'})
        packet=configurable_packet(); packet.update(connection())
        packet['slot_info']['1']['game']=GAME
        await client.handle(socket,packet)
        client.notifications.configure({'scope':'off','seconds':8})
        await client.handle(socket,{'cmd':'DataPackage','data':{'games':{'Other':{'item_name_to_id':{'Sword':10}}}}})
        outgoing=event(); outgoing['item']['flags']=1
        await client.handle(socket,outgoing)
        await client.handle(socket,{'cmd':'ReceivedItems','index':0,'items':[
            {'item':SUPPLY_DROP_ID,'location':-1,'player':0,'flags':2}]})
        await client.handle(socket,{'cmd':'PrintJSON','data':[{'text':'Cheat console: sending "Supply Drop" to One'}]})
        coloured=[r for r in caplog.records if hasattr(r,'item_parts')]
        assert any(r.getMessage()=='You sent Sword to Friend' and r.item_parts[1]==('Sword','#AF99EF') for r in coloured)
        assert not any(r.getMessage().startswith('Received:') for r in caplog.records)
        assert any(r.getMessage()=='Server sent Supply Drop to You' and r.item_parts[1]==('Supply Drop','#00EEEE') for r in coloured)
        assert len(coloured) == 2
        assert not client.notifications.queue  # Log output does not enable toasts.
    caplog.set_level('INFO',logger='ZeroHour')
    asyncio.run(run())


@pytest.mark.parametrize('kind', ['ItemSend','ItemCheat','server_send'])
@pytest.mark.parametrize('recipient', [1,2])
@pytest.mark.parametrize('receipt_first', [True,False])
def test_each_live_transfer_logs_once_in_either_packet_order(tmp_path,caplog,kind,recipient,receipt_first):
    from zh.mission_data import GAME, SUPPLY_DROP_ID
    async def run():
        client=ZeroHourClient('localhost:1','test',state_dir=tmp_path); socket=Socket()
        await client.handle(socket,{'cmd':'RoomInfo','seed_name':'single-transfer'})
        packet=configurable_packet(); packet.update(connection())
        for slot in ('1','2'): packet['slot_info'][slot]['game']=GAME
        await client.handle(socket,packet)
        await client.handle(socket,{'cmd':'ReceivedItems','index':0,'items':[]})
        caplog.clear()
        notice=event(2 if recipient==1 else 1,recipient,SUPPLY_DROP_ID,100 if kind=='ItemSend' else -1,kind)
        if kind=='server_send':
            notice={'cmd':'PrintJSON','data':[{'text':f'Cheat console: sending "Supply Drop" to {"One" if recipient==1 else "Two"}'}]}
        receipt={'cmd':'ReceivedItems','index':0,'items':[
            {'item':SUPPLY_DROP_ID,'location':100 if kind=='ItemSend' else -1,'player':2,'flags':0}]}
        sequence=([receipt] if recipient==1 else [])
        sequence.insert(len(sequence) if receipt_first else 0,notice)
        for part in sequence: await client.handle(socket,part)
        records=[r for r in caplog.records if hasattr(r,'item_parts')]
        assert len(records)==1
        assert records[0].getMessage().endswith(' sent Supply Drop to '+('You' if recipient==1 else 'Friend'))
        assert records[0].item_parts[1]==('Supply Drop','#00EEEE')
        assert not any(r.getMessage().startswith('Received:') for r in caplog.records)
        if recipient==1:
            assert client.inventory.count(SUPPLY_DROP_ID)==1
            # Resynchronizing inventory doesn't replay the transfer.
            await client.handle(socket,receipt)
            assert len([r for r in caplog.records if hasattr(r,'item_parts')])==1
        if kind!='ItemSend':
            # Two intentional identical cheat grants are still two deliveries.
            await client.handle(socket,notice)
            assert len([r for r in caplog.records if hasattr(r,'item_parts')])==2
    caplog.set_level('INFO',logger='ZeroHour')
    asyncio.run(run())
