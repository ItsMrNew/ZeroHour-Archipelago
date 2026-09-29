"""Exercise hook installation against real Windows allocation/protection bounds.

Only allocates in this test process; never attaches to or executes code in a game.
"""
import ctypes as ct
from ctypes import wintypes as wt
import os
from types import SimpleNamespace

import pytest

from test_power import InstallGame
from zh.power import PowerOutage
from zh.memory import kernel, MemoryReadError


def configured_hook(kind):
    game = InstallGame(0x567B98)
    if kind == 'menu':
        from zh.unlock_menu import UnlockMenu, SIGNATURES
        hook = UnlockMenu(game, None, [])
        for rva, raw in SIGNATURES.items():
            game.store(game.base + rva, bytes.fromhex(raw))
    elif kind == 'deathlink':
        from zh.deathlink import MissionRestart
        hook = MissionRestart(game)
    elif kind == 'combat':
        from zh.consumables import CombatEffects, NATIVE_SIGNATURES, reinforcement, sell_building
        from zh.generals_points import SIGNATURES
        hook = CombatEffects(game, generals=True)
        for rva, raw in (*NATIVE_SIGNATURES, *reinforcement.SIGNATURES, *sell_building.SIGNATURES, *SIGNATURES):
            game.store(game.base + rva, bytes.fromhex(raw))
    else:
        hook = PowerOutage(game)
    rva, layout = next(iter(hook.layouts.items()))
    game.original = game.base + rva
    game.put(game.logic, game.original)
    game.put(game.original - 4, 0)
    for i, target in enumerate(layout):
        game.put(game.original + i * 4, game.base + target)
    rva, raw = hook.signature
    game.store(game.base + rva, raw)
    return game, hook


@pytest.mark.skipif(os.name != 'nt', reason='Windows process-memory API')
@pytest.mark.parametrize('kind', ['menu', 'deathlink', 'power', 'combat'])
def test_installer_respects_real_windows_allocation_bounds(kind):
    game, hook = configured_hook(kind)
    api = kernel()
    game.pid = os.getpid()
    allocation = []
    def allocate(handle, address, size, flags, protection):
        # Callback bytes contain x86 addresses. Reserve a free low address in our
        # own process, even when the tests themselves use a 64-bit Python.
        for candidate in range(0x30000000, 0x40000000, 0x1000000):
            result = api.VirtualAllocEx(handle, candidate, size, flags, protection)
            if result:
                allocation.append((result, size))
                return result
        raise AssertionError('No low-address test allocation was available')
    fake_read, fake_store = game.read, game.store
    def in_allocation(address, size):
        return bool(allocation and allocation[0][0] <= address
                    and address + size <= sum(allocation[0]))
    def read(address, size):
        return ct.string_at(address, size) if in_allocation(address, size) else fake_read(address, size)
    def store(address, data):
        if in_allocation(address, len(data)):
            ct.memmove(address, data, len(data))
        else:
            fake_store(address, data)
    game.read, game.store = read, store
    game.api = SimpleNamespace(**{name: getattr(api, name) for name in
        ('OpenProcess', 'CloseHandle', 'WriteProcessMemory', 'VirtualProtectEx', 'FlushInstructionCache')},
        VirtualAllocEx=allocate)
    try:
        hook.install(SimpleNamespace(logic=game.logic))
        assert game.pointer(game.logic) == hook.table
        assert not hook.install_failed
        extra = hook.extra_pages(hook.region, hook.mailbox)
        assert bool(extra) == (kind in ('power', 'combat'))
        for address, data in extra.items():
            assert read(address, len(data)) == data
        if kind != 'menu':
            hook.close()
            assert game.pointer(game.logic) == game.original
        else:
            hook.close()
            assert game.pointer(hook.mailbox) == 2
    finally:
        # The test never executes any allocated callback, so immediate free is safe.
        if allocation:
            api.VirtualFreeEx.argtypes = [wt.HANDLE, ct.c_void_p, ct.c_size_t, wt.DWORD]
            api.VirtualFreeEx.restype = wt.BOOL
            handle = api.OpenProcess(0x8, False, game.pid)
            try:
                assert api.VirtualFreeEx(handle, allocation[0][0], 0, 0x8000)
            finally:
                api.CloseHandle(handle)


def test_out_of_bounds_extra_page_rejected_before_writing_or_publishing():
    game, hook = configured_hook('power')
    hook.allocation_size = 0x5000  # reproduce the menu allocation from the broken preview
    writes = []
    game.api.WriteProcessMemory = lambda *args: writes.append(args)
    with pytest.raises(MemoryReadError, match='outside its allocated'):
        hook.install(SimpleNamespace(logic=game.logic))
    assert writes == []
    assert game.pointer(game.logic) == game.original


@pytest.mark.parametrize('kind', ['menu', 'deathlink'])
def test_non_power_installers_do_not_require_radar_layout(kind, monkeypatch):
    from zh import radar_outage
    game, hook = configured_hook(kind)
    monkeypatch.setattr(radar_outage, 'validate', lambda *_: pytest.fail('Unexpected radar dependency'))
    monkeypatch.setattr(radar_outage, 'detach', lambda *_: pytest.fail('Unexpected radar cleanup'))
    hook.install(SimpleNamespace(logic=game.logic))
    hook.close()
