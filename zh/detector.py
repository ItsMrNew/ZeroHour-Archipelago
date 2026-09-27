from dataclasses import dataclass

from .mission_data import ALL_BY_CAMPAIGN_MISSION


@dataclass(frozen=True)
class Snapshot:
    campaign: str | None = None
    mission: str | None = None
    map_name: str | None = None
    victorious: bool = False


class VictoryDetector:
    """Require an observed non-victorious mission before accepting its victory.

    The score screen advances currentMission before the next game starts, so
    a victory belongs to the last observed *playing* mission, not that pointer.
    Connecting at an old victory screen must never award a check.
    """

    def __init__(self):
        self.armed = None

    def reset(self):
        self.armed = None

    def observe(self, snapshot: Snapshot) -> int | None:
        if snapshot.campaign not in {key[0] for key in ALL_BY_CAMPAIGN_MISSION}:
            self.reset()
            return None
        if not snapshot.victorious:
            mission = ALL_BY_CAMPAIGN_MISSION.get((snapshot.campaign, snapshot.mission))
            if mission and snapshot.map_name == mission["map"]:
                self.armed = mission
            else:
                self.reset()
            return None
        armed, self.armed = self.armed, None
        if not armed or armed["campaign"] != snapshot.campaign:
            return None
        # Allow the just-completed mission or the score screen's next mission.
        allowed = {armed["mission"], armed["next_mission"]}
        if snapshot.mission not in allowed:
            return None
        return armed["id"]

