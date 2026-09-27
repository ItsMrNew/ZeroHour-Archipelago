from datetime import datetime

import pytest

from zh.mission_data import ALL_MISSIONS
from zh.mission_saves import (MissionSave, all_saves, create_save, parse_challenge,
                              GENERALS, DIFFICULTIES)


def test_pack_has_every_mission_on_every_difficulty_with_native_restart_format():
    saves = all_saves(datetime(2026, 9, 19, 12))
    assert len(saves) == 240
    assert len({save.description for _, save in saves}) == 240
    for difficulty in DIFFICULTIES:
        selected = [save for level, save in saves if level == difficulty]
        assert len(selected) == 80
        assert sum(bool(s.challenge_data) for s in selected) == 65
        assert {(s.campaign, s.mission) for s in selected} == {(m['campaign'], m['mission']) for m in ALL_MISSIONS}
        for save in selected:
            data = save.encode()
            assert MissionSave.decode(data) == save
            assert data.count(b'CHUNK_') == 2  # never a GameLogic/Player/object snapshot
            assert save.difficulty == DIFFICULTIES.index(difficulty)
            assert save.description.startswith(f'Archipelago - {difficulty} - ')
            assert save.mission_index == int(save.mission[-2:]) - 1
            assert len(data) < 1200
            if save.challenge_data:
                challenge = parse_challenge(save.challenge_data)
                assert save.player_template == GENERALS[save.campaign][1]
                assert challenge['slots'][0][0] == 5
                assert challenge['slots'][0][3][2] == save.player_template
                assert challenge['slots'][0][3][6] == save.player_template
                assert all(slot[0] == 1 for slot in challenge['slots'][1:])
                assert challenge['map'] == save.map_name
                assert challenge['cash'] == 10000


def test_user_naming_examples_and_boss_match_actual_campaign_order():
    names = {s.description for _, s in all_saves()}
    assert 'Archipelago - Easy - USA 1' in names
    assert 'Archipelago - Easy - Infantry 1 - Vs. Air' in names
    assert 'Archipelago - Hard - GLA 5' in names
    assert 'Archipelago - Medium - Demolition 8 - Vs. Leang' in names
    assert 'Archipelago - Easy - Air 1 - Vs. Toxin' in names


@pytest.mark.parametrize('damage', ['truncated', 'trailing', 'normal', 'chunk_length'])
def test_rejects_bad_files_and_normal_snapshots(damage):
    data = bytearray(create_save(ALL_MISSIONS[0], 'Easy').encode())
    if damage == 'truncated': data = data[:-1]
    elif damage == 'trailing': data += b'junk'
    elif damage == 'normal': data[21:25] = b'\0' * 4
    else: data[16:20] = b'\xff' * 4
    with pytest.raises(ValueError):
        MissionSave.decode(bytes(data))
