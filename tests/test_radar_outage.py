"""Run the actual x86 minimap wrappers with mission-forced/disable-proof radar."""
import struct
import pytest
from unicorn.x86_const import UC_X86_REG_ESP, UC_X86_REG_EAX
from test_power import Simulation
from zh import radar_outage as r


class RadarSimulation(Simulation):
    radar, window = 0x2208000, 0x220A000
    def __init__(self):
        super().__init__()
        self.put(self.base + r.RADAR, self.radar)
        self.put(self.radar + r.WINDOW, self.window)
        self.put(self.window + r.DRAW_FIELD, self.base + r.DRAW)
        self.put(self.window + r.INPUT_FIELD, self.base + r.INPUT)
        self.uc.mem_write(self.base + r.DRAW, bytes.fromhex('b888000000c3'))
        self.uc.mem_write(self.base + r.INPUT, bytes.fromhex('b899000000c3'))

    def start(self):
        self.run()  # issue the trap; its native expiry is 1200
        self.run()  # following update attaches the local HUD callbacks

    def callback(self, field):
        self.uc.reg_write(UC_X86_REG_ESP, self.stack)
        self.put(self.stack, self.base + 0x123)
        self.uc.reg_write(UC_X86_REG_EAX, 0x77)
        self.uc.emu_start(self.get(self.window + field), self.base + 0x123, count=1000)
        assert self.uc.reg_read(UC_X86_REG_ESP) == self.stack + 4
        return self.uc.reg_read(UC_X86_REG_EAX)


@pytest.mark.parametrize('forced', [False, True])
def test_outage_blocks_drawing_and_clicks_even_when_radar_forced(forced):
    game = RadarSimulation()
    game.uc.mem_write(game.radar + 0xC, bytes([0, int(forced)]))
    game.start()
    assert game.callback(r.DRAW_FIELD) == 0x77  # stock draw was not called
    assert game.callback(r.INPUT_FIELD) == 1  # click swallowed
    assert bytes(game.uc.mem_read(game.radar + 0xC, 2)) == bytes([0, int(forced)])
    assert game.get(game.player + 0x84) == 20  # no power-provider edits
    assert game.get(game.player + 0x88) == 10


def test_pause_keeps_minimap_blocked_and_expiry_restores_callbacks():
    game = RadarSimulation(); game.start()
    for _ in range(4):
        game.run()  # no simulation-frame advancement while paused
        assert game.callback(r.INPUT_FIELD) == 1
    game.put(game.logic + 0x3C, 1200)
    # Even before maintenance runs, the wrappers must stop blocking at expiry.
    assert game.callback(r.DRAW_FIELD) == 0x88
    game.run()
    assert game.get(game.mailbox + r.TIMER) == 0
    assert game.get(game.window + r.DRAW_FIELD) == game.base + r.DRAW
    assert game.get(game.window + r.INPUT_FIELD) == game.base + r.INPUT


@pytest.mark.parametrize('change', ['load_map', 'load_save', 'new_game', 'rewind', 'mission', 'player', 'victory', 'mode'])
def test_transition_clears_minimap_suppression(change):
    game = RadarSimulation(); game.start()
    where = {'load_map': (game.logic + 0x51, 1), 'load_save': (game.logic + 0x52, 1),
             'new_game': (game.logic + 0x64, 1), 'rewind': (game.logic + 0x3C, 299),
             'mission': (game.manager + 12, 999), 'player': (game.players + 12, game.player + 4),
             'victory': (game.manager + 16, 1), 'mode': (game.logic + 0x94, 1)}
    game.put(*where[change]); game.run()
    assert game.get(game.mailbox + r.TIMER) == 0
    assert game.get(game.window + r.DRAW_FIELD) == game.base + r.DRAW
    assert game.get(game.window + r.INPUT_FIELD) == game.base + r.INPUT


def test_second_trap_extends_radar_blackout_to_native_expiry():
    game = RadarSimulation(); game.start()
    game.put(game.logic + 0x3C, 1000)
    game.put(game.mailbox, 1); game.run()
    assert game.get(game.mailbox + r.TIMER) == game.get(game.player + 0x8C) == 2100
    game.put(game.logic + 0x3C, 1300); game.run()
    assert game.callback(r.INPUT_FIELD) == 1


def test_foreign_callback_is_not_replaced():
    game = RadarSimulation()
    game.put(game.window + r.DRAW_FIELD, game.base + 0x1234)
    game.start()
    assert game.get(game.window + r.DRAW_FIELD) == game.base + 0x1234
    assert game.get(game.window + r.INPUT_FIELD) == game.base + r.INPUT


def test_external_timer_clear_restores_callbacks_on_next_update():
    game = RadarSimulation(); game.start()
    game.put(game.mailbox + r.TIMER, 0)
    game.run()
    assert game.get(game.window + r.DRAW_FIELD) == game.base + r.DRAW
    assert game.get(game.window + r.INPUT_FIELD) == game.base + r.INPUT


def test_disconnect_detaches_only_owned_callbacks():
    game = RadarSimulation(); game.start()
    class Memory:
        base = game.base
        pointer = staticmethod(game.get)
        @staticmethod
        def replace_pointer(address, expected, value):
            assert game.get(address) == expected
            game.put(address, value)
    r.detach(Memory(), game.code, game.mailbox)
    assert game.get(game.mailbox + r.TIMER) == 0
    assert game.get(game.window + r.INPUT_FIELD) == game.base + r.INPUT
    assert game.get(game.window + r.DRAW_FIELD) == game.base + r.DRAW
