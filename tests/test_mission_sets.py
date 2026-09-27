import asyncio
import random
from types import SimpleNamespace

import pytest
from unicorn.x86_const import UC_X86_REG_ECX, UC_X86_REG_ESP

from zh.mission_data import (MISSION_SETS, SET_BONUSES, SET_ITEMS, MISSIONS, ALL_MISSIONS,
    ALL_CHECKS, select_missions, with_set_bonuses, choose_starting_sets, earned_set_bonuses)
from zh.missiongate import MissionControl, EXIT_RVA, MESSAGE_RVA, TRANSLATE_RVA
from zh.deathlink import build_restart_stub
from zh.client import ZeroHourClient, IncompatibleRoom
from test_client import Socket
from test_deathlink import death_packet, state
from test_effects import inventory, Game
from test_quickreset import CheckpointSimulation


def packet(starting=('usa',), exclude=False):
    data = death_packet()
    missions = select_missions(disable_unit_only=exclude)
    ids = {m['id'] for m in with_set_bonuses(missions)}
    data['slot_data'].update(protocol_version=8, death_link_mode='quick_reset',
        mission_set_unlocks={k: MISSION_SETS[k]['item_id'] for k in ('usa','gla','china')},
        starting_sets=list(starting), set_completion_checks=5, location_ids=sorted(ids),
        disable_unit_only_missions=exclude)
    data.update(missing_locations=sorted(ids), checked_locations=[])
    return data


def test_set_ids_unique_and_counts_preserve_all_mission_locations():
    assert len(SET_ITEMS) == 12 and len(SET_BONUSES) == 120
    assert len({m['id'] for m in ALL_CHECKS}) == 920
    assert len(ALL_MISSIONS) == 80
    assert len(with_set_bonuses(select_missions())) == 30
    assert len(with_set_bonuses(select_missions(disable_unit_only=True))) == 28


@pytest.mark.parametrize('count', range(1, 13))
def test_start_count_random_unique_and_clamped_to_enabled_sets(count):
    challenges, starts = choose_starting_sets(['USA','GLA','China'], 9, [], count, random.Random(1))
    assert len(challenges) == 9 and len(set(starts)) == count
    _, starts = choose_starting_sets(['USA'], 0, [], count, random.Random(2))
    assert starts == ['usa']


def test_chosen_generals_are_included_and_other_starts_are_random():
    challenges, starts = choose_starting_sets(['USA'], 3, ['USA','GLA Stealth'], 3, random.Random(1))
    stealth = next(k for k,v in MISSION_SETS.items() if v['label']=='GLA Stealth')
    assert stealth in challenges and {stealth,'usa'} <= set(starts) and len(starts)==3


@pytest.mark.parametrize('campaigns,generals,chosen,count', [
    (['USA'],0,['GLA'],1), (['USA'],0,['GLA Stealth'],1),
    (['USA','GLA'],0,['USA','GLA'],1), (['USA'],0,['bad'],1), (['USA'],0,[],0)])
def test_impossible_start_choices_rejected(campaigns,generals,chosen,count):
    with pytest.raises(ValueError):choose_starting_sets(campaigns,generals,chosen,count,random.Random(0))


@pytest.mark.parametrize('key', list(MISSION_SETS))
def test_five_extra_checks_only_after_every_included_mission(key):
    missions = tuple(m for m in ALL_MISSIONS if m['campaign']==key)
    ids = {m['id'] for m in missions}
    assert not earned_set_bonuses(missions, ids-{missions[-1]['id']})
    assert len(earned_set_bonuses(missions,ids))==5


def test_protocol_bonus_persistence_lock_guard_and_excluded_missions(tmp_path):
    async def run():
        c=ZeroHourClient('localhost:1','test',state_dir=tmp_path);sock=Socket()
        await c.handle(sock,{'cmd':'RoomInfo','seed_name':'sets'})
        await c.handle(sock,packet(exclude=True))
        usa=[m['id'] for m in c.selected_missions if m['campaign']=='usa']
        c.victory(usa[0]);assert not c.progress.completed
        c.inventory=inventory(MISSION_SETS['usa']['item_id']);c.inventory_confirmed=True
        for i in usa[:-1]:c.victory(i)
        assert len(c.progress.completed)==3
        c.victory(usa[-1]);assert len(c.progress.completed)==9
        c.victory(usa[-1]);assert len(c.progress.completed)==9
        china=next(m['id'] for m in MISSIONS if m['campaign']=='china')
        c.victory(china);assert china not in c.progress.completed
        restored=ZeroHourClient('localhost:1','test',state_dir=tmp_path)
        await restored.handle(sock,{'cmd':'RoomInfo','seed_name':'sets'})
        await restored.handle(sock,packet(exclude=True))
        assert restored.progress.completed==c.progress.completed
    asyncio.run(run())


class GateSimulation(CheckpointSimulation):
    def __init__(self, action):
        super().__init__(action)
        self.uc.mem_write(self.code,build_restart_stub(self.base,self.code,self.mailbox,quick=True,gate=True))
        for rva,code in [(EXIT_RVA,b'\xc3'),(MESSAGE_RVA,b'\xc3'),
                          (TRANSLATE_RVA,b'\xc2\x04\0'),(0x380F60,b'\xc3')]:
            self.uc.mem_write(self.base+rva,code)
    def observe(self,uc,address,size,user_data):
        esp=uc.reg_read(UC_X86_REG_ESP)
        if address==self.base+TRANSLATE_RVA:
            assert uc.reg_read(UC_X86_REG_ECX)==esp+8
            assert self.get(esp+4)==esp+12 and self.get(esp+12)==0x123456
            self.put(esp+8,0x654321);self.calls.append('translate')
        elif address==self.base+MESSAGE_RVA:
            assert self.get(esp+4)==self.ui and self.get(esp+8)==0x654321
            self.calls.append('message')
        elif address==self.base+0x380F60:
            assert uc.reg_read(UC_X86_REG_ECX)==esp+4 and self.get(esp+4)==0x123456
            self.calls.append('destroy_ascii')
        elif address==self.base+EXIT_RVA:self.calls.append('exit_mission')
        else:super().observe(uc,address,size,user_data)


def test_native_lock_message_owns_strings_and_preserves_gui_stack():
    g=GateSimulation(3);g.run();g.run()
    assert g.calls==['string','translate','message','destroy_ascii'] and g.get(g.mailbox)==2


def test_native_exit_dispatch_does_not_call_restart_save_load_or_defeat():
    g=GateSimulation(4);g.run();g.run()
    assert g.calls==['exit_mission'] and g.get(g.mailbox)==2


@pytest.mark.parametrize('change', ['loading','mission','mode','defeat','rewound'])
def test_gate_native_scene_guards(change):
    g=GateSimulation(4)
    addr,value={'loading':(g.logic+0x51,1),'mission':(g.manager+12,0),
                'mode':(g.logic+0x94,1),'defeat':(g.scripts+0x10AA4,120),
                'rewound':(g.logic+0x3C,0)}[change]
    g.put(addr,value);g.run();assert not g.calls and g.get(g.mailbox)==3


def test_unlock_during_notice_cancels_scheduled_exit(monkeypatch):
    control=MissionControl(Game());requests=[]
    monkeypatch.setattr(control,'_queue',lambda st,action,**kw:requests.append(action) or True)
    control.enforce(state(),'locked');assert requests==[3]
    control.exit_at=0
    control.enforce(state(),None)
    assert control.exit_at is None and not control.enforce(state(),None)
    assert requests==[3]


def test_exit_only_after_notice_delay_and_once(monkeypatch):
    control=MissionControl(Game());requests=[]
    monkeypatch.setattr(control,'_queue',lambda st,action,**kw:requests.append(action) or True)
    monkeypatch.setattr('zh.missiongate.time.monotonic',lambda:100)
    control.enforce(state(),'locked');control.exit_at=105
    control.enforce(state(),'locked');assert requests==[3]
    monkeypatch.setattr('zh.missiongate.time.monotonic',lambda:106)
    control.enforce(state(),'locked');control.enforce(state(),'locked')
    assert requests==[3,4]
