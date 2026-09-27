import asyncio
import json

import pytest

from test_check_counts import configurable_packet
from test_client import Socket
from test_unlock_menu import MenuSimulation
from zh.client import ZeroHourClient
from zh.deathlink_options import DEFAULT_SELECTION, resolve, selected_event, menu_labels, validate_selection
from zh.game_options import DEFAULTS
from zh.memory import MemoryReadError
from zh.state import Progress
from zh.unlock_menu import ROW_DEFS, ROWS, STRIDE, SELECTED_COLOR


@pytest.mark.parametrize('enabled', [False, True])
@pytest.mark.parametrize('yaml_mode', ['full_restart', 'quick_reset'])
def test_overrides_and_return_to_yaml(enabled, yaml_mode):
    yaml = (enabled, yaml_mode, 60)
    assert resolve(DEFAULT_SELECTION, yaml) == (enabled, yaml_mode, 60 if enabled else 0)
    for event, mode in ((53, 'full_restart'), (54, 'quick_reset')):
        selected = selected_event(DEFAULT_SELECTION, event)
        assert resolve(selected, yaml) == (True, mode, 60)
        assert resolve(selected_event(selected, 57), yaml) == (True, mode, 0)
        assert resolve(selected_event(selected, 58), yaml) == (True, mode, 30)
        assert resolve(selected_event(selected, 52), yaml)[0] is False
        assert selected_event(selected, 51) == DEFAULT_SELECTION


def test_duration_bounds_validation_and_labels():
    for value in (None, {}, {**DEFAULT_SELECTION, 'seconds': True}, {**DEFAULT_SELECTION, 'seconds': 301}):
        with pytest.raises(ValueError): validate_selection(value)
    for duration in (1, 30, 300):
        selected = {**DEFAULT_SELECTION, 'seconds': duration}
        for event in (59, 60):
            result = selected_event(selected, event)
            assert result['grace'] == 'on' and 1 <= result['seconds'] <= 300
    labels = menu_labels(DEFAULT_SELECTION, (True, 'quick_reset', 300), 9000)
    assert labels[51][1] == labels[56][1] == 3
    assert all(len(text.encode('ascii')) < 64 for text, _ in labels.values())


def test_preferences_are_durable_isolated_and_backward_compatible(tmp_path, monkeypatch):
    p = Progress(tmp_path, 'seed', 0, 1)
    selected = selected_event(DEFAULT_SELECTION, 54)
    p.save_deathlink_selection(selected)
    assert Progress(tmp_path, 'seed', 0, 1).deathlink_selection == selected
    assert Progress(tmp_path, 'seed', 0, 2).deathlink_selection == DEFAULT_SELECTION
    monkeypatch.setattr(p, 'save', lambda *args: (_ for _ in ()).throw(OSError('disk full')))
    with pytest.raises(OSError): p.save_deathlink_selection(DEFAULT_SELECTION)
    assert p.deathlink_selection == selected
    data = json.loads(p.path.read_text()); del data['deathlink_selection']
    p.path.write_text(json.dumps(data))
    assert Progress(tmp_path, 'seed', 0, 1).deathlink_selection == DEFAULT_SELECTION


def test_live_tags_grace_pending_links_and_reconnect(tmp_path, monkeypatch):
    async def run():
        client = ZeroHourClient('localhost:1', 'test', state_dir=tmp_path)
        socket = Socket()
        await client.handle(socket, dict(cmd='RoomInfo', seed_name='live'))
        packet = configurable_packet()
        packet['slot_data'].update(protocol_version=16, death_link=False,
            death_link_mode='full_restart', game_options={**DEFAULTS, 'death_link_grace_seconds':60})
        await client.handle(socket, packet)
        assert not client.death_link and client.death_grace_seconds == 0
        client.deathlink_event(54)
        await client.sync_deathlink_tags(socket)
        assert socket.packets[-1] == {'cmd':'ConnectUpdate', 'tags':['AP','DeathLink']}
        assert client.death_link and client.death_link_mode == 'quick_reset'
        await client.handle(socket, packet)  # YAML comparison must ignore manual override.
        assert client.death_link_mode == 'quick_reset'
        client.grace_remaining = 1500
        client.deathlink_event(57)
        assert client.death_grace_seconds == client.grace_remaining == 0
        client.deathlink_event(58)
        assert client.death_grace_seconds == 30 and client.grace_remaining == 0
        client.death_active = client.death_received = client.death_outgoing = object()
        client.deathlink_event(52)
        assert client.death_active is client.death_received is client.death_outgoing is None
        await client.sync_deathlink_tags(socket)
        assert socket.packets[-1] == {'cmd':'ConnectUpdate', 'tags':['AP']}
        count = len(socket.packets)
        await client.sync_deathlink_tags(socket)
        assert len(socket.packets) == count
        monkeypatch.setattr(client.progress, 'save', lambda *args: (_ for _ in ()).throw(OSError('disk full')))
        with pytest.raises(MemoryReadError): client.deathlink_event(53)
        assert not client.death_link and client.progress.deathlink_selection['mode'] == 'off'
    asyncio.run(run())


def test_native_deathlink_tab_events_and_selection_colour():
    sim = MenuSimulation()
    labels = menu_labels(DEFAULT_SELECTION, (False, 'full_restart', 0), 0)
    for n, row in enumerate(ROW_DEFS):
        if row[0] in labels:
            sim.put(sim.mailbox + ROWS + n * STRIDE + 28, labels[row[0]][1])
    sim.tick(); sim.click(1); sim.click(7); sim.tick()
    assert sim.get(sim.mailbox + 20) == 3
    assert not sim.get(sim.window(51) + 4) & 16
    assert sim.get(sim.window(10) + 4) & 16
    assert sim.get(sim.window(40) + 4) & 16
    assert sim.get(sim.window(51) + 0x48) == SELECTED_COLOR
    for event in (51, 52, 53, 54, 56, 57, 58, 59, 60):
        sim.put(sim.mailbox + 12, 0); sim.click(event)
        assert sim.get(sim.mailbox + 12) == event
