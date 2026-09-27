import asyncio
import json

import pytest
from websockets.asyncio.server import serve

from zh.client import IncompatibleRoom, ZeroHourClient, server_url
from zh.mission_data import GAME, ITEM_ID, LOCATION_IDS, DOZER_ITEM_ID, DOZER_ITEM_NAME, BUILDER_ITEMS
from zh.state import Progress


class Socket:
    def __init__(self):
        self.packets = []

    async def send(self, data):
        self.packets.extend(json.loads(data))


def connected(checked=()):
    return {"cmd": "Connected", "team": 0, "slot": 1,
            "checked_locations": list(checked), "missing_locations": sorted(LOCATION_IDS - set(checked)),
            "slot_data": {"protocol_version": 1, "goal": "all_campaign_missions", "location_ids": sorted(LOCATION_IDS)}}


def test_wrong_world_and_changed_seed_fail_closed(tmp_path):
    async def test():
        client = ZeroHourClient("localhost:1", "test", state_dir=tmp_path)
        socket = Socket()
        await client.handle(socket, {"cmd": "RoomInfo", "seed_name": "seed1"})
        bad = connected()
        bad["slot_data"]["protocol_version"] = 2
        with pytest.raises(IncompatibleRoom):
            await client.handle(socket, bad)
        await client.handle(socket, connected())
        with pytest.raises(IncompatibleRoom):
            await client.handle(socket, {"cmd": "RoomInfo", "seed_name": "seed2"})
    asyncio.run(test())


def test_real_websocket_handshake_outbox_and_goal_acknowledgement(tmp_path):
    async def test():
        received = []
        finished = asyncio.Event()
        first, *rest = sorted(LOCATION_IDS)
        # A win saved during an earlier disconnect must be resent on connection.
        Progress(tmp_path, "test-seed", 0, 1).mark(first)

        async def server(socket):
            await socket.send(json.dumps([{"cmd": "RoomInfo", "seed_name": "test-seed"}]))
            async for raw in socket:
                for packet in json.loads(raw):
                    received.append(packet)
                    if packet["cmd"] == "Connect":
                        assert packet["game"] == GAME and packet["items_handling"] == 7
                        await socket.send(json.dumps([connected()]))
                    elif packet["cmd"] == "LocationChecks":
                        checks = set(packet["locations"])
                        assert checks <= LOCATION_IDS
                        assert not any(p["cmd"] == "StatusUpdate" for p in received)
                        await socket.send(json.dumps([{"cmd": "RoomUpdate", "checked_locations": sorted(checks)}]))
                        if checks == {first}:
                            for location in rest:
                                client.victory(location)
                    elif packet["cmd"] == "StatusUpdate":
                        assert packet["status"] == 30
                        assert client.acknowledged == LOCATION_IDS
                        finished.set()

        async with serve(server, "127.0.0.1", 0) as server_instance:
            port = server_instance.sockets[0].getsockname()[1]
            client = ZeroHourClient(f"127.0.0.1:{port}", "test", state_dir=tmp_path)
            task = asyncio.create_task(client.network())
            try:
                await asyncio.wait_for(finished.wait(), 5)
            finally:
                task.cancel()
                await asyncio.gather(task, return_exceptions=True)
        assert Progress(tmp_path, "test-seed", 0, 1).completed == LOCATION_IDS
    asyncio.run(test())


@pytest.mark.parametrize("address", ["", "https://host", "ws://user:secret@host", "host:wrong"])
def test_invalid_server_address(address):
    with pytest.raises(ValueError):
        server_url(address)


@pytest.mark.parametrize(("address", "expected"), [
    ("archipelago.gg:63006", "wss://archipelago.gg:63006"),
    ("ARCHIPELAGO.GG:63006", "wss://ARCHIPELAGO.GG:63006"),
    ("room.archipelago.gg:12345", "wss://room.archipelago.gg:12345"),
    ("localhost:38281", "ws://localhost:38281"),
    ("127.0.0.1:38281", "ws://127.0.0.1:38281"),
    ("ws://archipelago.gg:63006", "ws://archipelago.gg:63006"),
    ("wss://example.org:12345", "wss://example.org:12345"),
    ("archipelago.gg.example.org:12345", "ws://archipelago.gg.example.org:12345"),
])
def test_hosted_tls_default_preserves_local_and_explicit_schemes(address, expected):
    assert server_url(address) == expected


def test_receipt_synchronization_persistence_and_gap_recovery(tmp_path):
    async def test():
        client = ZeroHourClient("localhost:1", "test", state_dir=tmp_path)
        socket = Socket()
        await client.handle(socket, {"cmd": "RoomInfo", "seed_name": "receipts"})
        await client.handle(socket, connected())
        item = {"item": ITEM_ID, "location": min(LOCATION_IDS), "player": 1, "flags": 0}
        await client.handle(socket, {"cmd": "ReceivedItems", "index": 0, "items": [item]})
        assert client.inventory.count(ITEM_ID) == 1
        assert len(Progress(tmp_path, "receipts", 0, 1).received) == 1
        await client.handle(socket, {"cmd": "ReceivedItems", "index": 2, "items": [item]})
        assert socket.packets[-2]["cmd"] == "Sync"
        assert socket.packets[-1]["cmd"] == "LocationChecks"
        assert client.inventory.count(ITEM_ID) == 1
        await client.handle(socket, {"cmd": "ReceivedItems", "index": 0, "items": [item]})
        assert client.inventory.synchronized
        assert client.inventory.count(ITEM_ID) == 1
        client.victory(min(LOCATION_IDS))
        assert len(Progress(tmp_path, "receipts", 0, 1).received) == 1
    asyncio.run(test())


def test_receipt_before_authentication_fails(tmp_path):
    async def test():
        client = ZeroHourClient("localhost:1", "test", state_dir=tmp_path)
        with pytest.raises(IncompatibleRoom):
            await client.handle(Socket(), {"cmd": "ReceivedItems", "index": 0, "items": []})
    asyncio.run(test())


def test_dozer_requires_new_slot_and_authoritative_inventory(tmp_path):
    async def test():
        client = ZeroHourClient("localhost:1", "test", state_dir=tmp_path)
        socket = Socket()
        await client.handle(socket, {"cmd": "RoomInfo", "seed_name": "dozer"})
        packet = connected()
        packet['slot_data'].update(protocol_version=2, unit_unlocks=[DOZER_ITEM_NAME])
        await client.handle(socket, packet)
        assert client.dozer_mode and not client.inventory_confirmed
        item = {"item": DOZER_ITEM_ID, "location": -2, "player": 1, "flags": 2}
        await client.handle(socket, {"cmd": "ReceivedItems", "index": 0, "items": [item]})
        assert client.inventory_confirmed and client.inventory.count(DOZER_ITEM_ID) == 1
        await client.handle(socket, {"cmd": "ReceivedItems", "index": 3, "items": [item]})
        assert not client.inventory_confirmed
        await client.handle(socket, {"cmd": "ReceivedItems", "index": 0, "items": []})
        assert client.inventory_confirmed and client.inventory.count(DOZER_ITEM_ID) == 0
        await client.handle(socket, connected())
        assert not client.dozer_mode  # Old rooms never enable the write adapter.
    asyncio.run(test())


def test_dozer_failure_does_not_disarm_victory_detection(tmp_path, monkeypatch):
    from zh import client as module
    from zh.detector import Snapshot
    from zh.memory import MemoryReadError

    class Game:
        pid = 123
        path = tmp_path / 'Game.dat'
        states = iter([Snapshot('usa', 'mission01', 'maps/md_usa01/md_usa01.map', False),
                       Snapshot('usa', 'mission01', 'maps/md_usa01/md_usa01.map', True)])

        def snapshot(self):
            state = next(self.states, None)
            if state is None:
                raise asyncio.CancelledError
            return state

        def close(self):
            pass

    class FailingDozer:
        def __init__(self, game):
            pass

        def apply(self, unlocked):
            raise MemoryReadError('Test: command layout unavailable')

        def restore(self):
            pass

    async def no_sleep(seconds):
        pass

    monkeypatch.setattr(module.GameMemory, 'find', lambda: Game())
    monkeypatch.setattr(module, 'DozerUnlock', FailingDozer)
    monkeypatch.setattr(module.asyncio, 'sleep', no_sleep)
    client = ZeroHourClient('localhost:1', 'test', state_dir=tmp_path)
    client.progress = Progress(tmp_path, 'independent-checks', 0, 1)
    client.dozer_mode = client.inventory_confirmed = True
    with pytest.raises(asyncio.CancelledError):
        asyncio.run(client.watch())
    assert client.progress.completed == {min(LOCATION_IDS)}


def test_builder_protocol_authentication_and_independent_receipts(tmp_path):
    async def test():
        client = ZeroHourClient('localhost:1', 'test', state_dir=tmp_path)
        socket = Socket()
        await client.handle(socket, {'cmd': 'RoomInfo', 'seed_name': 'builders'})
        packet = connected()
        packet['slot_data'].update(protocol_version=3, unit_unlocks=list(BUILDER_ITEMS.values()))
        with pytest.raises(IncompatibleRoom):
            await client.handle(socket, packet)
        packet['slot_data']['builder_scope'] = 'all_stock_campaign_command_centers'
        await client.handle(socket, packet)
        assert client.builder_mode and not client.dozer_mode and not client.inventory_confirmed
        for index, item in enumerate(BUILDER_ITEMS):
            await client.handle(socket, {'cmd': 'ReceivedItems', 'index': index,
                                        'items': [{'item': item, 'location': -2, 'player': 1, 'flags': 2}]})
            assert client.inventory.count(item) == 1
            assert sum(client.inventory.count(i) for i in BUILDER_ITEMS) == index + 1
        assert client.inventory_confirmed
    asyncio.run(test())


def test_selected_missions_ignore_exclusions_and_preserve_configuration_on_reconnect(tmp_path):
    from zh.mission_data import select_missions, BY_KEY

    async def test():
        client = ZeroHourClient('localhost:1', 'test', state_dir=tmp_path)
        socket = Socket()
        await client.handle(socket, {'cmd': 'RoomInfo', 'seed_name': 'selected'})
        selected = {m['id'] for m in select_missions(['USA'], True, ['challenge_8'])}
        packet = connected()
        packet['missing_locations'] = sorted(selected)
        packet['slot_data'].update(protocol_version=4, goal='all_selected_missions',
            unit_unlocks=list(BUILDER_ITEMS.values()), builder_scope='all_stock_campaign_command_centers',
            enabled_campaigns=['USA'], disable_unit_only_missions=True,
            selected_challenges=['challenge_8'], location_ids=sorted(selected))
        await client.handle(socket, packet)
        client.victory(BY_KEY['usa_03']['id'])
        client.victory(BY_KEY['gla_01']['id'])
        assert not client.progress.completed
        for location in selected:
            client.victory(location)
        assert client.progress.completed == selected
        await client.handle(socket, {'cmd': 'RoomUpdate', 'checked_locations': sorted(selected)})
        task = asyncio.create_task(client.flush(socket))
        await asyncio.sleep(0)
        await asyncio.sleep(0)
        await asyncio.sleep(0)
        task.cancel()
        await asyncio.gather(task, return_exceptions=True)
        assert any(p['cmd'] == 'StatusUpdate' and p['status'] == 30 for p in socket.packets)
        # A same-slot reconnect may not silently change required missions.
        packet['slot_data']['disable_unit_only_missions'] = False
        packet['slot_data']['location_ids'] += [BY_KEY['usa_03']['id']]
        packet['missing_locations'] += [BY_KEY['usa_03']['id']]
        with pytest.raises(IncompatibleRoom, match='selection changed'):
            await client.handle(socket, packet)
    asyncio.run(test())


def test_effect_capability_requires_protocol_five_and_exact_settings(tmp_path):
    from zh.mission_data import EFFECT_CONFIG, CASH_ITEM_ID, POWER_TRAP_ID

    async def test():
        client = ZeroHourClient('localhost:1', 'test', state_dir=tmp_path)
        socket = Socket()
        await client.handle(socket, {'cmd': 'RoomInfo', 'seed_name': 'effects'})
        packet = connected()
        packet['slot_data'].update(protocol_version=5, goal='all_selected_missions',
            unit_unlocks=list(BUILDER_ITEMS.values()), builder_scope='all_stock_campaign_command_centers',
            enabled_campaigns=['USA', 'China', 'GLA'], disable_unit_only_missions=False,
            selected_challenges=[])
        with pytest.raises(IncompatibleRoom, match='effect configuration'):
            await client.handle(socket, packet)
        packet['slot_data']['effects'] = dict(EFFECT_CONFIG)
        await client.handle(socket, packet)
        assert client.effects_mode and not client.inventory_confirmed
        receipts = [{'item': code, 'location': -2, 'player': 1, 'flags': flag}
                    for code, flag in [(CASH_ITEM_ID, 2), (POWER_TRAP_ID, 4)]]
        await client.handle(socket, {'cmd': 'ReceivedItems', 'index': 0, 'items': receipts})
        client.progress.reserve_effects([0, 1])
        await client.handle(socket, {'cmd': 'ReceivedItems', 'index': 0, 'items': receipts})
        assert client.inventory_confirmed and len(client.inventory.items) == 2
        assert client.progress.effect_receipts == {0, 1}
        packet['slot_data']['protocol_version'] = 4
        await client.handle(socket, packet)
        assert not client.effects_mode
    asyncio.run(test())
