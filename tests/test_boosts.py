import struct
from types import SimpleNamespace

import pytest
from unicorn import UC_HOOK_CODE
from unicorn.x86_const import UC_X86_REG_EAX, UC_X86_REG_ECX, UC_X86_REG_ESP

from zh import boosts as b, consumables as c
from zh.gameplay import INPUT_OFFSET
from zh.mission_data import PRODUCTION_SURGE_ID, CONSTRUCTION_BOOST_ID
from test_consumables_native import CombatSimulation
from test_effects import setup


@pytest.mark.parametrize('operation,timer', [(8,b.PRODUCTION),(9,b.CONSTRUCTION)])
def test_boosts_last_120_control_seconds_extend_and_clear(operation,timer):
    sim=CombatSimulation(operation)
    sim.put(sim.mailbox+12, b.DURATION*30)
    sim.run()
    assert sim.get(sim.mailbox+timer)==3900
    sim.put(sim.mailbox,1);sim.run()
    assert sim.get(sim.mailbox+timer)==7500
    sim.put(0x220D000+INPUT_OFFSET,0)
    sim.put(sim.logic+0x3C,600);sim.run()
    assert sim.get(sim.mailbox+timer)==7800
    sim.put(0x220D000+INPUT_OFFSET,1)
    sim.put(sim.logic+0x3C,7799);sim.run()
    assert sim.get(sim.mailbox+timer)==7800
    sim.put(sim.logic+0x3C,7800);sim.run()
    assert sim.get(sim.mailbox+timer)==0


@pytest.mark.parametrize('operation,timer', [(8,b.PRODUCTION),(9,b.CONSTRUCTION)])
@pytest.mark.parametrize('change',['loading','save','newgame','rewind','mission','player','mode','victory'])
def test_boost_lifecycle_cannot_leak_into_other_missions(operation,timer,change):
    sim=CombatSimulation(operation);sim.put(sim.mailbox+12,3600);sim.run()
    changes={'loading':(sim.logic+0x51,1),'save':(sim.logic+0x52,1),
        'newgame':(sim.logic+0x64,1),'rewind':(sim.logic+0x3C,299),
        'mission':(sim.manager+12,sim.mission+4),'player':(sim.players+12,0),
        'mode':(sim.logic+0x94,1),'victory':(sim.manager+16,1)}
    sim.put(*changes[change]);sim.run()
    assert sim.get(sim.mailbox+timer)==0


def invoke(sim,address,this):
    stop=sim.code+0xF00
    sim.put(sim.stack,stop)
    sim.uc.reg_write(UC_X86_REG_ECX,this)
    sim.uc.reg_write(UC_X86_REG_ESP,sim.stack)
    sim.uc.emu_start(address,stop,count=3000)
    assert sim.uc.reg_read(UC_X86_REG_ESP)==sim.stack+4
    return sim.uc.reg_read(UC_X86_REG_EAX)


@pytest.mark.parametrize('case',['own_unit','enemy','upgrade','empty','expired','cutscene','shutdown'])
def test_production_doubles_only_local_unit_progress_and_obeys_shutdown(case):
    sim=CombatSimulation(8);sim.put(sim.mailbox+12,3600);sim.run()
    interface,entry=0x220B000,0x220C000
    sim.put(interface+0x18,0 if case=='empty' else entry)
    sim.put(interface-8,sim.anchor);sim.put(entry+4,2 if case=='upgrade' else 1)
    sim.put(entry+0x14,100)
    sim.owner=sim.player+4 if case=='enemy' else sim.player
    if case=='expired':sim.put(sim.logic+0x3C,3900)
    if case=='cutscene':sim.put(0x220D000+INPUT_OFFSET,0)
    if case=='shutdown':
        sim.put(sim.mailbox+28,2);sim.put(sim.mailbox,1);sim.run()
    # Stand-in models the game's verified frames-under-construction increment.
    sim.uc.mem_write(sim.base+c.PRODUCTION_UPDATE_RVA,bytes.fromhex('8b411885c07403ff4014b87b000000c3'))
    result=invoke(sim,sim.code+c.PRODUCTION_CODE_OFFSET,interface)
    assert result==(1 if case=='shutdown' else 123)
    assert sim.get(entry+0x14)==(102 if case=='own_unit' else 100 if case in ('empty','shutdown') else 101)


@pytest.mark.parametrize('case',['own_builder','enemy','expired','cutscene','no_boost','invalid_factor'])
@pytest.mark.parametrize('factor',[0.5,1.0,1.5,2.0])
def test_construction_wraps_native_builder_checks_and_restores_exact_handicap(case,factor):
    sim=CombatSimulation(9);sim.put(sim.mailbox+12,3600);sim.run()
    state,machine=0x220B000,0x220C000
    sim.put(state+0x20,machine);sim.put(machine+0x14,sim.anchor)
    sim.owner=sim.player+4 if case=='enemy' else sim.player
    bits=0x7fc00000 if case=='invalid_factor' else struct.unpack('<I',struct.pack('<f',factor))[0]
    sim.put(sim.player+b.BUILDING_TIME,bits)
    if case=='expired':sim.put(sim.logic+0x3C,3900)
    if case=='cutscene':sim.put(0x220D000+INPUT_OFFSET,0)
    if case=='no_boost':sim.put(sim.mailbox+b.CONSTRUCTION,0)
    observed=[]
    def native(uc,address,size,data):
        if address==sim.base+b.DOZER_UPDATE:
            assert uc.reg_read(UC_X86_REG_ECX)==state
            observed.append(sim.get(sim.player+b.BUILDING_TIME))
    sim.uc.hook_add(UC_HOOK_CODE,native)
    sim.uc.mem_write(sim.base+b.DOZER_UPDATE,bytes.fromhex('b87b000000c3'))
    assert invoke(sim,sim.code+b.CONSTRUCTION_CODE,state)==123
    assert observed==[bits-0x800000 if case=='own_builder' else bits]
    assert sim.get(sim.player+b.BUILDING_TIME)==bits


@pytest.mark.parametrize('item,operation', [(PRODUCTION_SURGE_ID,8),(CONSTRUCTION_BOOST_ID,9)])
def test_received_boosts_wait_for_control_and_reserve_once(tmp_path,monkeypatch,item,operation):
    game,progress,inv,effects=setup(tmp_path,item);effects.expanded=True
    calls=[]
    class Native:
        busy=False
        def __init__(self,game): pass
        def poll(self): return []
        def prepare(self,state,count,operation): calls.append((count,operation))
        def arm(self): calls.append('armed')
    monkeypatch.setattr('zh.effects.CombatEffects',Native)
    game.input=b'\0';effects.apply(inv)
    assert not progress.effect_receipts and not calls
    game.input=b'\1';effects.apply(inv);effects.apply(inv)
    assert progress.effect_receipts=={0}
    assert calls==[(1,operation),'armed']


@pytest.mark.parametrize('op', [8,9])
def test_boost_requests_also_wait_for_control_on_game_thread(op):
    sim=CombatSimulation(op);sim.put(sim.mailbox+12,3600)
    sim.put(0x220D000+INPUT_OFFSET,0);sim.run()
    assert sim.get(sim.mailbox)==1
    assert not sim.get(sim.mailbox+b.PRODUCTION) and not sim.get(sim.mailbox+b.CONSTRUCTION)
    sim.put(0x220D000+INPUT_OFFSET,1);sim.run()
    assert sim.get(sim.mailbox)==2


@pytest.mark.parametrize('operation',[8,9])
def test_boost_installation_and_disconnect_restore_native_tables(operation):
    from test_power import InstallGame
    game=InstallGame(0x567B98)
    for rva,prefix in (*c.NATIVE_SIGNATURES,*c.reinforcement.SIGNATURES,*c.sell_building.SIGNATURES):
        game.store(game.base+rva,bytes.fromhex(prefix))
    game.store(game.base+c.PRODUCTION_TABLE_RVA,struct.pack('<II',game.base+c.PRODUCTION_UPDATE_RVA,game.base+0x1A0390))
    game.put(game.base+b.DOZER_TABLE+16,game.base+b.DOZER_UPDATE)
    effect=c.CombatEffects(game)
    state=SimpleNamespace(logic=game.logic,player=game.player,frame=300,mission=('usa','mission01'))
    effect.prepare(state,1,operation)
    assert game.pointer(effect.mailbox+12)==3600
    if operation==9: assert game.pointer(game.base+b.DOZER_TABLE+16)==effect.region+b.CONSTRUCTION_CODE
    else: assert game.pointer(game.base+c.PRODUCTION_TABLE_RVA)==effect.region+c.PRODUCTION_CODE_OFFSET
    effect.close()
    assert game.pointer(game.base+b.DOZER_TABLE+16)==game.base+b.DOZER_UPDATE
    assert game.pointer(game.base+c.PRODUCTION_TABLE_RVA)==game.base+c.PRODUCTION_UPDATE_RVA
    assert not game.pointer(effect.mailbox+b.PRODUCTION) and not game.pointer(effect.mailbox+b.CONSTRUCTION)


def test_boost_protocol_and_filler_colours(tmp_path):
    import asyncio
    from test_check_counts import configurable_packet
    from test_client import Socket
    from zh.client import ZeroHourClient,IncompatibleRoom
    from zh.game_options import DEFAULTS
    from zh.mission_data import BOOST_CONFIG,ABILITY_CONFIG
    from zh.notifications import local_item_flags,item_colour
    async def check():
        client=ZeroHourClient('localhost:1','Test',state_dir=tmp_path)
        sock=Socket()
        await client.handle(sock,{'cmd':'RoomInfo','seed_name':'boosts'})
        packet=configurable_packet()
        packet['slot_data'].update(protocol_version=18,boosts=BOOST_CONFIG,abilities=ABILITY_CONFIG,game_options=DEFAULTS)
        await client.handle(sock,packet)
        assert client.consumables_mode
        packet['slot_data']['boosts']={**BOOST_CONFIG,'duration_seconds':60}
        with pytest.raises(IncompatibleRoom,match='boost configuration'):
            await client.handle(sock,packet)
    asyncio.run(check())
    for item in (PRODUCTION_SURGE_ID,CONSTRUCTION_BOOST_ID):
        assert local_item_flags(item)==0
        assert item_colour(local_item_flags(item))=='#00EEEE'
