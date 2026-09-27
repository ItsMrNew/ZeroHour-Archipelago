"""Permanent ability inventory, durable cooldowns, and shared effect dispatch."""
import math
import logging

from .ability_native import map_bounds
from .consumables import CombatEffects
from .gameplay import input_enabled
from .mission_data import ABILITY_ITEMS, REVEAL_MINIMAP_ID, CARPET_BOMB_ID, PATRIOT_AIRDROP_ID, EMERGENCY_REPAIR_ID

LOG = logging.getLogger(__name__)
COOLDOWNS = {REVEAL_MINIMAP_ID: 5400, CARPET_BOMB_ID: 7200, PATRIOT_AIRDROP_ID: 9000, EMERGENCY_REPAIR_ID: 7200}
OPERATIONS = {REVEAL_MINIMAP_ID: 3, CARPET_BOMB_ID: 4, PATRIOT_AIRDROP_ID: 6, EMERGENCY_REPAIR_ID: 7}


class AbilityController:
    def __init__(self, effects, enabled):
        self.effects, self.enabled = effects, set(enabled)
        self.progress = effects.progress
        self.remaining = dict(self.progress.ability_cooldowns)
        self.last = None
        self.unsaved_frames = 0
        self.pending = None
        self.state = None

    def cooldown(self, item):
        return COOLDOWNS[item] * getattr(self.effects, "options", {}).get("ability_cooldown_percent", 100) // 100

    def suspend(self):
        self.last = self.state = None
        self.flush()

    def flush(self):
        if self.remaining != self.progress.ability_cooldowns:
            self.progress.save_cooldowns(self.remaining)
        self.unsaved_frames = 0

    def tick(self):
        power = self.effects.power
        if isinstance(power, CombatEffects) and power.ability_result is not None:
            operation, status = power.ability_result
            power.ability_result = None
            if self.pending is not None and operation == OPERATIONS[self.pending]:
                if status == 3:
                    self.remaining[ABILITY_ITEMS[self.pending]] = 0
                    self.flush()
                self.pending = None
        state = self.effects.snapshot()
        if (state is None or not state.player or state.loading_map or state.loading_save
                or not input_enabled(self.effects.game)):
            self.suspend()
            return
        key = (state.logic, state.player, state.mission)
        if self.last and self.last[0] == key:
            delta = state.frame - self.last[1]
            # A load can jump forward as well as rewind. Never convert a missed
            # session into free cooldown time; regular polls are 0.25 seconds.
            if 0 < delta <= 90:
                self.remaining = {name: max(0, value - delta) for name, value in self.remaining.items()}
                self.unsaved_frames += delta
                if self.unsaved_frames >= 30:
                    self.flush()
        self.last = (key, state.frame)
        self.state = state

    def ready(self, item, inventory):
        return (item in self.enabled and inventory.synchronized and inventory.count(item) > 0
                and self.state is not None and self.pending is None
                and not self.remaining.get(ABILITY_ITEMS[item], 0))

    def label(self, item, inventory):
        name = ABILITY_ITEMS[item]
        if item not in self.enabled:
            return f'N/A: {name}', 0
        if not inventory.count(item):
            return f'Locked: {name}', 0
        seconds = math.ceil(self.remaining.get(name, 0) / 30)
        if seconds:
            return f'{name}: {seconds // 60}:{seconds % 60:02}', 0
        return f'Ready: {name}', 3 if self.ready(item, inventory) else 0

    def cast(self, item, inventory, target=None):
        if not self.ready(item, inventory):
            return False
        effects = self.effects
        if effects.power is None:
            effects.power = CombatEffects(effects.game)
        power = effects.power
        if power.busy or not power.reported:
            return False
        bounds = map_bounds(effects.game)
        if item == REVEAL_MINIMAP_ID:
            target = tuple((bounds[i] + bounds[i + 3]) / 2 for i in range(3))
            radius = math.hypot(bounds[3] - bounds[0], bounds[4] - bounds[1]) / 2 + 100
        elif target is None:
            return False
        else:
            radius = 100 if item == EMERGENCY_REPAIR_ID else 250
        effects.check_same(self.state)
        power.prepare_ability(self.state, OPERATIONS[item],
                              target, radius, 450 if item == REVEAL_MINIMAP_ID else 1200)
        # Reserve before publishing; uncertain native execution cannot replay.
        updated = dict(self.remaining)
        updated[ABILITY_ITEMS[item]] = self.cooldown(item)
        self.progress.save_cooldowns(updated)
        self.remaining = updated
        self.pending = item
        power.arm()
        LOG.info('%s requested from the Archipelago menu.', ABILITY_ITEMS[item])
        return True
