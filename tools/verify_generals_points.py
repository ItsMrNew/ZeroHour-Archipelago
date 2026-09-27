"""Check world generation and client negotiation against an Archipelago source tree.

Usage: python tools/verify_generals_points.py PATH_TO_ARCHIPELAGO
Loads only Zero Hour, using real AP classes, without discovering unrelated games.
"""
import asyncio
from collections import Counter
from pathlib import Path
import sys
import tempfile
import types

ROOT = Path(__file__).resolve().parents[1]


def main(ap):
    sys.path[:0] = [str(ROOT), str(ap)]
    worlds = types.ModuleType('worlds')
    worlds.__path__ = [str(ROOT / 'worlds'), str(ap / 'worlds')]
    sys.modules['worlds'] = worlds
    from BaseClasses import MultiWorld, CollectionState, ItemClassification
    from worlds.generals_zh import ZeroHourWorld, ZeroHourOptions
    from zh.client import ZeroHourClient, IncompatibleRoom
    from zh.mission_data import GENERALS_POINT_NAME, GENERALS_CONFIG

    def make(enabled, points, challenges=2, mission_checks=1, set_checks=5, **extra):
        mw = MultiWorld(1)
        mw.set_seed(123)
        w = ZeroHourWorld(mw, 1)
        mw.worlds[1] = w
        mw.game[1] = w.game
        mw.player_name = {1: 'Test'}
        overrides = dict(progressive_generals_powers=enabled, generals_point_items=points,
                         generals_challenge_campaigns=challenges, mission_completion_checks=mission_checks,
                         set_completion_checks=set_checks)
        overrides.update(extra)
        w.options = ZeroHourOptions(**{n: t.from_any(overrides.get(n, t.default))
                                      for n, t in ZeroHourOptions.type_hints.items()})
        mw.state = CollectionState(mw)
        w.generate_early()
        w.create_regions()
        w.create_items()
        w.set_rules()
        return mw, w

    class Socket:
        async def send(self, data): pass

    async def negotiate(w, enabled, directory):
        c = ZeroHourClient('localhost:1', 'Test', state_dir=directory)
        sock = Socket()
        await c.handle(sock, {'cmd': 'RoomInfo', 'seed_name': 'points-test'})
        slot = w.fill_slot_data()
        packet = dict(cmd='Connected', team=0, slot=1, slot_data=slot,
                      checked_locations=[], missing_locations=slot['location_ids'])
        await c.handle(sock, packet)
        assert c.generals_mode is enabled
        await c.handle(sock, packet)  # reconnect preserves the configuration
        for bad in ('yes', None, int(not enabled), not enabled):
            slot['progressive_generals_powers'] = bad
            try: await c.handle(sock, packet)
            except IncompatibleRoom: pass
            else: raise AssertionError('Invalid/changed mode accepted')
        slot['progressive_generals_powers'] = enabled
        slot['generals_points'] = {**GENERALS_CONFIG, 'rank_thresholds': [1,2,3,4,5]}
        try: await c.handle(sock, packet)
        except IncompatibleRoom: pass
        else: raise AssertionError('Unknown rank thresholds accepted')

    with tempfile.TemporaryDirectory(prefix='zh-points-') as directory:
        for enabled in (False, True):
            for points in range(29):
                mw, w = make(enabled, points)
                counts = Counter(i.name for i in mw.itempool)
                assert counts[GENERALS_POINT_NAME] == (points if enabled else 0)
                assert len(mw.itempool) == len(mw.get_locations())
                assert all(i.classification == ItemClassification.useful for i in mw.itempool
                           if i.name == GENERALS_POINT_NAME)
                if points in (0,18,28):
                    asyncio.run(negotiate(w, enabled, Path(directory) / f'{enabled}-{points}'))
        for mission_checks in range(1,11):
            for set_checks in range(11):
                mw, w = make(False, 18, mission_checks=mission_checks, set_checks=set_checks)
                expected = len(w.selected_missions)*mission_checks + len(w.sets)*set_checks
                assert len(mw.itempool) == len(mw.get_locations()) == expected
                for name in ('power_outage_weight','cash_theft_weight','production_shutdown_weight','sell_random_building_weight'):
                    assert getattr(w.options, name).value == 50
                asyncio.run(negotiate(w, False, Path(directory) / f'counts-{mission_checks}-{set_checks}'))
        # Exercise new options against real Archipelago generation classes.
        for goal in ('all_sets', 'set_count', 'final_mission'):
            mw, w = make(True, 18, challenges=2, mission_checks=3, victory_goal=goal,
                goal_set_count=2, goal_final_set='challenge_7', starting_builders=['USA Dozer'],
                starting_abilities=['Patriot Airdrop'], starting_generals_points=7,
                power_outage_seconds=180, production_shutdown_seconds=5,
                cash_theft_percent=100, ability_cooldown_percent=300,
                death_link_grace_enabled=True, death_link_grace_seconds=60)
            assert len(mw.itempool)==len(w.selected_locations)
            counts=Counter(i.name for i in mw.itempool)
            assert counts[GENERALS_POINT_NAME]==11 and counts['USA Dozer']==0 and counts['Patriot Airdrop']==0
            pre=Counter(i.name for i in mw.precollected_items[1])
            assert pre[GENERALS_POINT_NAME]==7 and pre['USA Dozer']==1 and pre['Patriot Airdrop']==1
            assert w.fill_slot_data()['game_options']['cash_theft_percent']==100
            assert w.fill_slot_data()['game_options']['death_link_grace_seconds']==60
            if goal=='final_mission': assert 'challenge_7' in w.selected_challenges
            asyncio.run(negotiate(w, True, Path(directory)/goal))
        for extra in (dict(starting_generals_points=19),dict(starting_builders=['GLA Toxin Worker'],general_builder_unlocks=False),
                      dict(starting_abilities=['Reveal Minimap'],reveal_minimap=False),dict(victory_goal='set_count',goal_set_count=12)):
            try: make(True,18,**extra)
            except ValueError: pass
            else: raise AssertionError('Invalid new options accepted')
        try: make(True, 18, challenges=0)
        except ValueError as error: assert '18 Generals Point items' in str(error)
        else: raise AssertionError('Overfilled pool accepted')
        mw, w = make(False, 18, challenges=0)
        assert len(mw.itempool) == 30
        assert w.options.death_link_grace_enabled.value == 0
        assert w.fill_slot_data()['game_options']['death_link_grace_seconds'] == 0
        assert w.options.mission_report_weight.value==0
        assert w.options.supply_drop_weight.value==w.options.reinforcements_weight.value==50
        assert w.options.trap_percentage.value==50
        _,defaults=make(False,18,challenges=0,traps_enabled=True)
        from worlds.generals_zh.trap_pool import TRAP_NAMES
        assert sum(defaults.filler_counts[n] for n in TRAP_NAMES)==6
        assert defaults.filler_counts['Mission Report']==0
        assert defaults.filler_counts['Supply Drop']+defaults.filler_counts['Reinforcements']==6
        for repair, starting in ((True, []), (True, ['Emergency Repair']), (False, [])):
            mw, w = make(False, 18, challenges=0, emergency_repair=repair, starting_abilities=starting)
            counts = Counter(i.name for i in mw.itempool)
            assert counts['Emergency Repair'] == int(repair and not starting)
            assert len(mw.itempool) == len(w.selected_locations)
            assert ('Emergency Repair' in w.fill_slot_data()['ability_unlocks']) == repair
            assert w.create_item('Emergency Repair').classification == ItemClassification.useful
            assert Counter(i.name for i in mw.precollected_items[1])['Emergency Repair'] == int(bool(starting))
            asyncio.run(negotiate(w, False, Path(directory)/f'repair-{repair}-{bool(starting)}'))
        try: make(False,18, emergency_repair=False, starting_abilities=['Emergency Repair'])
        except ValueError: pass
        else: raise AssertionError('Disabled repair accepted as starting ability')
        for percentage in (0,50,100):
            mw,w=make(False,18,traps_enabled=True,trap_percentage=percentage,
                      progressive_starting_cash=3,mission_report_weight=0,
                      supply_drop_weight=25,reinforcements_weight=75)
            assert len(mw.itempool)==len(w.selected_locations)
            counts=Counter(i.name for i in mw.itempool)
            assert counts['Mission Report']==0
            assert counts['Supply Drop']==w.filler_counts['Supply Drop']
            assert counts['Reinforcements']==w.filler_counts['Reinforcements']
            assert counts['Progressive Starting Cash']==3
            from worlds.generals_zh.trap_pool import TRAP_NAMES
            assert sum(w.filler_counts[n] for n in TRAP_NAMES)==sum(w.filler_counts.values())*percentage//100
            assert all(i.classification==ItemClassification.filler for i in mw.itempool if i.name in ('Mission Report','Supply Drop','Reinforcements'))
            assert all(w.create_item(name).classification==ItemClassification.filler
                       for name in ('Mission Report','Supply Drop','Reinforcements'))
            asyncio.run(negotiate(w,False,Path(directory)/f'filler-{percentage}'))
        from worlds.generals_zh.Options import ZeroHourOptions, Reinforcements, SupplyDrops
        from Options import Visibility
        assert 'progress_tracker' not in ZeroHourOptions.type_hints
        assert Reinforcements.visibility == SupplyDrops.visibility == Visibility.none
        for key in ('reinforcements', 'supply_drops'):
            try: make(False,18,**{key:1})
            except ValueError as error: assert 'Useful Item Filler weights' in str(error)
            else: raise AssertionError('Obsolete fixed helpful counts accepted')
        for cash in range(11):
            mw, w = make(False,18,progressive_starting_cash=cash)
            assert Counter(i.name for i in mw.itempool)['Progressive Starting Cash']==cash
            assert w.fill_slot_data()['game_options']['progress_tracker'] is True
        _, w = make(False, 18, death_link_grace_seconds=90)
        assert w.fill_slot_data()['game_options']['death_link_grace_seconds'] == 0
    print('PASS: 58 point pools, 110 check-count pools, default trap weights, capacity validation, real world slot data, client handshake and reconnect checks.')


if __name__ == '__main__':
    main(Path(sys.argv[1]).resolve())
