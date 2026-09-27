import pytest

from zh.detector import Snapshot, VictoryDetector
from zh.mission_data import MISSIONS


def playing(mission):
    return Snapshot(mission["campaign"], mission["mission"], mission["map"], False)


@pytest.mark.parametrize("mission", MISSIONS)
def test_every_mission_reports_its_own_victory(mission):
    detector = VictoryDetector()
    assert detector.observe(playing(mission)) is None
    win = Snapshot(mission["campaign"], mission["mission"], mission["map"], True)
    assert detector.observe(win) == mission["id"]
    assert detector.observe(win) is None


@pytest.mark.parametrize("mission", MISSIONS)
def test_score_screen_advances_pointer_before_poll(mission):
    detector = VictoryDetector()
    detector.observe(playing(mission))
    number = int(mission["mission"][-2:])
    next_name = f"mission{number + 1:02}" if number < 5 else None
    assert detector.observe(Snapshot(mission["campaign"], next_name, None, True)) == mission["id"]


def test_attach_to_old_win_never_awards_check():
    detector = VictoryDetector()
    assert detector.observe(Snapshot("usa", "mission02", None, True)) is None


def test_loss_menu_challenge_and_modded_map_do_not_award():
    detector = VictoryDetector()
    first = MISSIONS[0]
    detector.observe(playing(first))
    assert detector.observe(playing(first)) is None  # a loss leaves victory false
    detector.observe(Snapshot())
    assert detector.observe(Snapshot("usa", "mission01", first["map"], True)) is None
    detector.observe(Snapshot("challenge_0", "mission01", first["map"], False))
    assert detector.observe(Snapshot("challenge_0", "mission02", None, True)) is None
    detector.observe(Snapshot("usa", "mission01", "maps/custom/custom.map", False))
    assert detector.observe(Snapshot("usa", "mission02", None, True)) is None


def test_campaign_switch_and_unexpected_jump_do_not_award():
    detector = VictoryDetector()
    detector.observe(playing(MISSIONS[0]))
    assert detector.observe(Snapshot("gla", "mission02", None, True)) is None
    detector.observe(playing(MISSIONS[0]))
    assert detector.observe(Snapshot("usa", "mission04", None, True)) is None

