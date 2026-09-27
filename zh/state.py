import hashlib
import json
import os
from pathlib import Path
import uuid

from .mission_data import ALL_LOCATION_IDS
from .inventory import ReceivedItem
from .deathlink_options import DEFAULT_SELECTION, validate_selection
from .notifications import DEFAULT_NOTIFICATIONS, validate_settings


class Progress:
    """A durable outbox isolated by server seed, team, and slot."""

    def __init__(self, directory: Path, seed: str, team: int, slot: int, location_ids=ALL_LOCATION_IDS):
        self.location_ids = frozenset(location_ids)
        self.identity = {"seed": seed, "team": team, "slot": slot}
        key = hashlib.sha256(json.dumps(self.identity, sort_keys=True).encode()).hexdigest()
        self.path = directory / f"{key}.json"
        self.completed: set[int] = set()
        self.received: tuple[ReceivedItem, ...] = ()
        self.effect_receipts = set()
        self.builder_choices = {}
        self.ability_cooldowns = {}
        self.deathlink_selection = dict(DEFAULT_SELECTION)
        self.notification_settings = dict(DEFAULT_NOTIFICATIONS)
        if self.path.exists():
            data = json.loads(self.path.read_text(encoding="utf-8"))
            if data.get("identity") != self.identity or data.get("version") != 1:
                raise ValueError(f"Invalid progress file: {self.path}")
            values = data.get("completed")
            if not isinstance(values, list) or any(type(v) is not int or v not in self.location_ids for v in values):
                raise ValueError(f"Invalid mission IDs in {self.path}")
            self.completed = set(values)
            received = data.get("received", [])
            if not isinstance(received, list):
                raise ValueError(f"Invalid received inventory in {self.path}")
            self.received = tuple(ReceivedItem.parse(value) for value in received)
            effects = data.get("effect_receipts", [])
            if not isinstance(effects, list) or any(type(i) is not int or i < 0 for i in effects):
                raise ValueError(f"Invalid effect receipt ledger in {self.path}")
            self.effect_receipts = set(effects)
            from .mission_data import BUILDER_CATALOG
            preferences = data.get('builder_choices', {})
            if (not isinstance(preferences, dict) or any(
                    family not in ('usa', 'china', 'gla') or
                    (item is not None and (type(item) is not int or item not in BUILDER_CATALOG
                                          or BUILDER_CATALOG[item][1] != family))
                    for family, item in preferences.items())):
                raise ValueError(f'Invalid builder choices in {self.path}')
            self.builder_choices = preferences
            cooldowns = data.get('ability_cooldowns', {})
            if (not isinstance(cooldowns, dict) or any(k not in ('Reveal Minimap', 'Carpet Bomb', 'Patriot Airdrop', 'Emergency Repair')
                    or type(v) is not int or not 0 <= v <= (27000 if k == 'Patriot Airdrop' else 21600) for k, v in cooldowns.items())):
                raise ValueError(f'Invalid ability cooldowns in {self.path}')
            self.ability_cooldowns = cooldowns
            self.deathlink_selection = validate_selection(data.get('deathlink_selection', DEFAULT_SELECTION))
            self.notification_settings = validate_settings(data.get('notification_settings', DEFAULT_NOTIFICATIONS))

    def save_notification_settings(self, values):
        previous = self.notification_settings
        self.notification_settings = validate_settings(values)
        try:
            self.save(self.completed, self.received)
        except Exception:
            self.notification_settings = previous
            raise

    def save_deathlink_selection(self, values):
        previous = self.deathlink_selection
        self.deathlink_selection = validate_selection(values)
        try:
            self.save(self.completed, self.received)
        except Exception:
            self.deathlink_selection = previous
            raise

    def save_cooldowns(self, values):
        previous = self.ability_cooldowns
        self.ability_cooldowns = dict(values)
        try:
            self.save(self.completed, self.received)
        except Exception:
            self.ability_cooldowns = previous
            raise

    def choose_builder(self, family, item):
        from .mission_data import BUILDER_CATALOG
        if family not in ('usa', 'china', 'gla') or (item is not None and
                (item not in BUILDER_CATALOG or BUILDER_CATALOG[item][1] != family)):
            raise ValueError('Invalid builder choice')
        previous = self.builder_choices.copy()
        self.builder_choices[family] = item
        try:
            self.save(self.completed, self.received)
        except Exception:
            self.builder_choices = previous
            raise

    def mark(self, location: int):
        if location not in self.location_ids:
            raise ValueError(f"Unknown mission check: {location}")
        self.merge({location})

    def merge(self, locations: set[int]):
        new = self.completed | (locations & self.location_ids)
        if new != self.completed:
            self.save(new, self.received)

    def record_inventory(self, received):
        received = tuple(received)
        if not all(isinstance(item, ReceivedItem) for item in received):
            raise ValueError("Invalid inventory")
        if received != self.received:
            self.save(self.completed, received)

    def reserve_effects(self, indices):
        """Persist intent before game writes: uncertain writes must never replay."""
        previous = self.effect_receipts.copy()
        self.effect_receipts.update(indices)
        try:
            self.save(self.completed, self.received)
        except Exception:
            self.effect_receipts = previous
            raise

    def save(self, completed, received):
        self.path.parent.mkdir(parents=True, exist_ok=True)
        temp = self.path.with_name(self.path.name + f".{uuid.uuid4().hex}.tmp")
        with temp.open("w", encoding="utf-8") as file:
            json.dump({"version": 1, "identity": self.identity, "completed": sorted(completed),
                       "received": [item.as_dict() for item in received],
                       "effect_receipts": sorted(self.effect_receipts),
                       "builder_choices": self.builder_choices,
                       "deathlink_selection": self.deathlink_selection,
                       "notification_settings": self.notification_settings,
                       "ability_cooldowns": self.ability_cooldowns}, file, indent=2)
            file.flush()
            os.fsync(file.fileno())
        os.replace(temp, self.path)
        self.completed = set(completed)
        self.received = tuple(received)
