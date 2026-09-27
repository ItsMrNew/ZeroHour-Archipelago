from itertools import product

import pytest

from zh.detector import Snapshot, VictoryDetector
from zh.mission_data import (CAMPAIGNS, MISSIONS, CHALLENGE_CAMPAIGNS, CHALLENGE_NAMES,
                             CHALLENGE_MISSIONS, ALL_MISSIONS, LOCATION_IDS, select_missions)
from zh.state import Progress


def test_stable_ids_and_actual_challenge_lengths():
    assert len(LOCATION_IDS) == 15
    assert len(CHALLENGE_MISSIONS) == 65
    assert [len(m) for _, _, m in CHALLENGE_CAMPAIGNS] == [7] * 7 + [8, 8]
    assert len({m['id'] for m in ALL_MISSIONS}) == 80
    assert len({m['name'] for m in ALL_MISSIONS}) == 80


@pytest.mark.parametrize('switches', list(product((False, True), repeat=4)))
@pytest.mark.parametrize('count', range(10))
def test_every_toggle_combination_and_challenge_count(switches, count):
    enabled = [c for c, on in zip(CAMPAIGNS, switches[:3]) if on]
    challenges = list(CHALLENGE_NAMES)[:count]
    if not enabled and not challenges:
        with pytest.raises(ValueError, match='Select at least'):
            select_missions(enabled, switches[3], challenges)
        return
    result = select_missions(enabled, switches[3], challenges)
    story = [m for m in result if not m['campaign'].startswith('challenge_')]
    removed = int('USA' in enabled) + int('GLA' in enabled) if switches[3] else 0
    assert len(story) == 5 * len(enabled) - removed
    assert len(result) == len(story) + sum(len(m) for c, _, m in CHALLENGE_CAMPAIGNS if c in challenges)
    assert all(m['campaign'] in {c.lower() for c in enabled} | set(challenges) for m in result)
    assert len(result) >= 3  # Existing three builder items always fit.


@pytest.mark.parametrize('mission', CHALLENGE_MISSIONS, ids=lambda m: m['key'])
@pytest.mark.parametrize('advance', [False, True])
def test_challenge_victories_before_and_after_score_screen(mission, advance):
    detector = VictoryDetector()
    assert detector.observe(Snapshot(mission['campaign'], mission['mission'], mission['map'], False)) is None
    end = Snapshot(mission['campaign'], mission['next_mission'] if advance else mission['mission'], None, True)
    assert detector.observe(end) == mission['id']
    assert detector.observe(end) is None


def test_same_opponent_different_playable_general_is_a_distinct_check():
    first = CHALLENGE_MISSIONS[0]
    second = next(m for m in CHALLENGE_MISSIONS if m['map'] == first['map'] and m['campaign'] != first['campaign'])
    assert first['id'] != second['id']
    detector = VictoryDetector()
    detector.observe(Snapshot(first['campaign'], first['mission'], first['map'], False))
    assert detector.observe(Snapshot(second['campaign'], second['mission'], second['map'], True)) is None


def test_progress_scoped_to_selected_checks(tmp_path):
    selected = {m['id'] for m in select_missions(['USA'], True, ['challenge_7'])}
    progress = Progress(tmp_path, 'selection', 0, 1, selected)
    disabled = next(m['id'] for m in MISSIONS if m['key'] == 'usa_03')
    with pytest.raises(ValueError):
        progress.mark(disabled)
    challenge = next(i for i in selected if i not in LOCATION_IDS)
    progress.mark(challenge)
    assert Progress(tmp_path, 'selection', 0, 1, selected).completed == {challenge}
