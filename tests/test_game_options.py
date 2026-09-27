import asyncio
from types import SimpleNamespace

import pytest

from test_check_counts import configurable_packet
from test_client import Socket
from test_effects import Game, inventory
from test_unlock_menu import MenuSimulation
from zh.client import ZeroHourClient, IncompatibleRoom
from zh.game_options import DEFAULTS, RANGES, validate_options, goal_reached, progress_lines
from zh.game_options import progress_view
from zh.mission_data import select_missions, with_set_bonuses, CASH_THEFT_ID, REVEAL_MINIMAP_ID
from zh.effects import PlayerEffects
from zh.abilities import AbilityController
from zh.state import Progress
from zh.unlock_menu import ROW_DEFS, ROWS, STRIDE


@pytest.mark.parametrize('key,bounds', RANGES.items())
def test_numeric_option_validation(key, bounds):
    missions = select_missions(challenges=tuple(f'challenge_{i}' for i in range(9)))
    for value in bounds:
        assert validate_options({**DEFAULTS, key:value}, missions)[key] == value
    for value in (bounds[0]-1, bounds[1]+1, True, '30', None):
        with pytest.raises(ValueError): validate_options({**DEFAULTS, key:value}, missions)


def test_goal_modes_and_excluded_missions():
    missions = select_missions(disable_unit_only=True)
    usa = {m['id'] for m in missions if m['campaign']=='usa'}
    assert len(usa)==4
    assert not goal_reached(DEFAULTS, missions, usa)
    assert goal_reached({**DEFAULTS, 'victory_goal':'set_count'}, missions, usa)
    assert not goal_reached({**DEFAULTS, 'victory_goal':'set_count','goal_set_count':2}, missions, usa)
    last = [m['id'] for m in missions if m['campaign']=='usa'][-1]
    assert goal_reached({**DEFAULTS, 'victory_goal':'final_mission'}, missions, {last})
    assert goal_reached(DEFAULTS, missions, {m['id'] for m in missions})
    with pytest.raises(ValueError): validate_options({**DEFAULTS,'victory_goal':'set_count','goal_set_count':4}, missions)


def test_client_negotiation_reconnect_and_legacy(tmp_path):
    async def run():
        c=ZeroHourClient('localhost:1','test',state_dir=tmp_path); sock=Socket()
        await c.handle(sock,dict(cmd='RoomInfo',seed_name='new-options'))
        packet=configurable_packet()
        packet['slot_data'].update(protocol_version=16,game_options={**DEFAULTS, 'cash_theft_percent':63})
        await c.handle(sock,packet); await c.handle(sock,packet)
        assert c.game_options['cash_theft_percent']==63
        packet['slot_data']['game_options']['cash_theft_percent']=64
        with pytest.raises(IncompatibleRoom, match='changed'): await c.handle(sock,packet)
        packet['slot_data']['game_options']['cash_theft_percent']=101
        with pytest.raises(IncompatibleRoom, match='Invalid'): await c.handle(sock,packet)
        old=ZeroHourClient('localhost:1','test',state_dir=tmp_path/'legacy')
        await old.handle(sock,dict(cmd='RoomInfo',seed_name='legacy'))
        await old.handle(sock,configurable_packet())
        assert old.game_options==DEFAULTS
    asyncio.run(run())


def test_grace_counts_only_bounded_playable_frames():
    c=ZeroHourClient('localhost:1','test'); c.grace_remaining=300
    state=lambda frame: SimpleNamespace(logic=1,campaign='usa',mission='mission01',frame=frame)
    c.tick_grace(state(100)); c.tick_grace(state(130)); assert c.grace_remaining==270
    c.tick_grace(None); c.tick_grace(state(190)); assert c.grace_remaining==270
    c.tick_grace(state(1000)); assert c.grace_remaining==270
    c.tick_grace(state(10)); assert c.grace_remaining==270
    for frame in range(40,311,30): c.tick_grace(state(frame))
    assert c.grace_remaining==0


@pytest.mark.parametrize('percent', [1,25,63,100])
def test_cash_theft_uses_percentage_without_cap(tmp_path, percent):
    game=Game(); game.values[game.player+0x38]=1234567
    progress=Progress(tmp_path,'theft',0,1)
    effects=PlayerEffects(game,progress,expanded=True,options={'cash_theft_percent':percent})
    effects.apply(inventory(CASH_THEFT_ID))
    assert game.pointer(game.player+0x38)==1234567-(1234567*percent//100)


def test_scaled_cooldown_persists(tmp_path):
    progress=Progress(tmp_path,'cooldown',0,1)
    effects=SimpleNamespace(progress=progress,options={'ability_cooldown_percent':300})
    abilities=AbilityController(effects,[REVEAL_MINIMAP_ID])
    assert abilities.cooldown(REVEAL_MINIMAP_ID)==16200
    progress.save_cooldowns({'Reveal Minimap':16200,'Patriot Airdrop':27000})
    assert Progress(tmp_path,'cooldown',0,1).ability_cooldowns==progress.ability_cooldowns


def test_tracker_counts_and_preserves_mission_numbers():
    missions=select_missions(disable_unit_only=True)
    checks=with_set_bonuses(missions,3,0)
    usa=[m for m in missions if m['campaign']=='usa']
    lines=progress_lines(missions,{usa[0]['id']},{m['id'] for m in checks},0)
    assert 'Checks 1/39' in lines[0]
    assert 'Mission 4: Pending' in '\n'.join(lines)
    assert 'Mission 3:' not in '\n'.join(lines)
    assert len(lines)==6 and all(len(line)<64 for line in lines)


def test_progress_logic_counts_all_configured_checks_and_unlocks():
    missions = select_missions(disable_unit_only=True)
    checks = with_set_bonuses(missions, 2, 5)
    locations = {m['id'] for m in checks}
    view = progress_view(missions, set(), locations, 0, {'usa'})
    assert (view['total'], view['remaining'], view['in_logic']) == (41, 41, 13)
    assert view['missions'][0] == ('Mission 1:', 'Pending', 'available')
    assert [m[0] for m in view['missions']] == ['Mission 1:', 'Mission 2:', 'Mission 4:', 'Mission 5:']
    usa = [m for m in missions if m['campaign'] == 'usa']
    completed = {m['id'] for m in checks if m.get('mission_id', m['id']) == usa[0]['id']}
    view = progress_view(missions, completed, locations, 0, {'usa'})
    assert (view['earned'], view['remaining'], view['in_logic']) == (2,39,11)
    assert view['missions'][0][1:] == ('DONE','complete')
    locked = progress_view(missions, completed, locations, 1, {'usa'})
    assert all(m[2] == 'locked' for m in locked['missions'])
    all_open = progress_view(missions, completed, locations, 0, {'usa','china','gla'})
    assert all_open['in_logic'] == all_open['remaining']
    assert progress_view(missions, locations, locations, 0, {'usa'})['in_logic'] == 0


def test_native_progress_tab_paging_and_disabled_visibility():
    sim=MenuSimulation(); sim.tick(); sim.click(1); sim.click(6); sim.tick()
    assert sim.get(sim.mailbox+20)==2
    assert not sim.get(sim.window(40)+4)&16
    assert sim.get(sim.window(10)+4)&16
    assert sim.get(sim.window(30)+4)&16
    sim.click(47); assert sim.get(sim.mailbox+12)==47
    sim.put(sim.mailbox+12,0); sim.click(46); assert sim.get(sim.mailbox+12)==46
    n=next(i for i,row in enumerate(ROW_DEFS) if row[0]==6)
    sim.put(sim.mailbox+ROWS+n*STRIDE+28,4); sim.tick()
    assert sim.get(sim.window(6)+4)&16


@pytest.mark.parametrize('seconds',[5,30,180])
def test_power_duration_reaches_native_mailbox(seconds):
    from test_power import InstallGame
    from zh.power import PowerOutage
    game=InstallGame(0x567B98)
    power=PowerOutage(game);power.power_seconds=seconds
    power.prepare(SimpleNamespace(logic=game.logic,player=game.player,frame=300),2)
    assert game.pointer(power.mailbox+12)==seconds*30*2


def test_goal_waits_for_acknowledgement_but_not_unrelated_sets(tmp_path):
    async def run():
        c=ZeroHourClient('localhost:1','test',state_dir=tmp_path)
        sock=Socket();await c.handle(sock,dict(cmd='RoomInfo',seed_name='goal'))
        packet=configurable_packet()
        packet['slot_data'].update(protocol_version=16,game_options={**DEFAULTS,'victory_goal':'final_mission'})
        await c.handle(sock,packet)
        last=[m['id'] for m in c.selected_missions if m['campaign']=='usa'][-1]
        c.progress.mark(last)
        sent=[]
        class Capture:
            async def send(self,data):
                import json
                sent.extend(json.loads(data))
        task=asyncio.create_task(c.flush(Capture()))
        await asyncio.sleep(.01)
        assert not any(p['cmd']=='StatusUpdate' for p in sent)
        c.acknowledged.add(last);c.changed.set();await asyncio.sleep(.01)
        assert any(p['cmd']=='StatusUpdate' and p['status']==30 for p in sent)
        task.cancel()
        try: await task
        except asyncio.CancelledError: pass
    asyncio.run(run())
