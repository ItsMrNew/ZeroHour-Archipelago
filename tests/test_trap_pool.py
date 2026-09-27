from collections import Counter
from random import Random

import pytest

from zh.mission_data import ITEM_NAME
from zh.trap_pool import TRAP_NAMES, make_filler_pool
from zh.trap_pool import FILLER_NAMES


@pytest.mark.parametrize('count', [0, 1, 7, 25, 131])
@pytest.mark.parametrize('percentage', [0, 1, 25, 50, 75, 99, 100])
def test_exact_pool_size_and_percentage_rounded_down(count, percentage):
    pool = make_filler_pool(count, True, percentage, [1, 1, 1, 1], Random(4))
    assert len(pool) == count
    assert sum(name in TRAP_NAMES for name in pool) == count * percentage // 100
    assert pool.count(ITEM_NAME) == count - count * percentage // 100


@pytest.mark.parametrize('weights', [[0, 0, 0, 0], [100, 10, 1, 1]])
def test_disabling_traps_preserves_all_filler(weights):
    assert make_filler_pool(25, False, 100, weights, Random(1)) == [ITEM_NAME] * 25


@pytest.mark.parametrize('selected', range(4))
def test_zero_weight_excludes_traps_even_at_full_replacement(selected):
    weights = [0, 0, 0, 0]
    weights[selected] = 1
    assert make_filler_pool(131, True, 100, weights, Random(1)) == [TRAP_NAMES[selected]] * 131


def test_seed_reproducible_and_relative_weights_control_distribution():
    first = make_filler_pool(10000, True, 100, [3, 1, 0, 0], Random(123))
    assert first == make_filler_pool(10000, True, 100, [3, 1, 0, 0], Random(123))
    assert first != make_filler_pool(10000, True, 100, [3, 1, 0, 0], Random(456))
    counts = Counter(first)
    assert 7300 < counts[TRAP_NAMES[0]] < 7700
    assert counts[TRAP_NAMES[2]] == 0


def test_all_zero_weights_report_actionable_error_only_when_needed():
    with pytest.raises(ValueError, match='weight above zero'):
        make_filler_pool(25, True, 50, [0, 0, 0, 0], Random(1))
    assert make_filler_pool(25, True, 0, [0, 0, 0, 0], Random(1)) == [ITEM_NAME] * 25


def test_impossible_helpful_item_budget_is_not_hidden_by_traps():
    with pytest.raises(ValueError, match='exceed'):
        make_filler_pool(-1, True, 100, [1, 1, 1, 1], Random(1))


@pytest.mark.parametrize('percentage', [0, 25, 50, 100])
@pytest.mark.parametrize('selected', range(3))
def test_weighted_filler_exclusion_exact_size_and_trap_priority(percentage, selected):
    weights=[0,0,0]; weights[selected]=50
    pool=make_filler_pool(17, True, percentage, [50]*4, Random(2), weights)
    traps=17*percentage//100
    assert len(pool)==17
    assert sum(n in TRAP_NAMES for n in pool)==traps
    assert pool.count(FILLER_NAMES[selected])==17-traps


def test_filler_ratios_reproducibility_and_disabled_traps():
    def make(seed): return make_filler_pool(10000, False, 100, [0]*4, Random(seed), [0,25,75])
    pool=make(123)
    assert pool==make(123) and pool!=make(456)
    counts=Counter(pool)
    assert counts[ITEM_NAME]==0 and 2300 < counts['Supply Drop'] < 2700
    assert counts['Supply Drop']+counts['Reinforcements']==10000


def test_empty_filler_weights_only_allowed_when_no_filler_slots_remain():
    with pytest.raises(ValueError, match='Non-trap filler'):
        make_filler_pool(1,False,100,[50]*4,Random(2),[0,0,0])
    assert len(make_filler_pool(17,True,100,[50]*4,Random(2),[0,0,0]))==17
    assert make_filler_pool(0,False,100,[50]*4,Random(2),[0,0,0])==[]
    for weights in ([1,2], [1,2,101], [True,0,0], [-1,0,0]):
        with pytest.raises(ValueError,match='Filler weights'):
            make_filler_pool(5,False,100,[50]*4,Random(2),weights)
