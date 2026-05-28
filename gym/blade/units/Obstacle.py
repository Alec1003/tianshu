from __future__ import annotations

from typing import Optional


class Obstacle:
    """Scenario-level environmental constraint zone.

    Obstacles are not combat units. They model training constraints such as
    no-go airspace, weather, difficult terrain, sensor shadow, or communication
    degradation. The backend simulation engine remains the source of truth for
    how these zones affect movement and detection.
    """

    def __init__(
        self,
        id: str,
        name: str,
        class_name: str,
        latitude: float,
        longitude: float,
        altitude: float = 0.0,
        radius_nm: float = 10.0,
        obstacle_type: str = "no_go",
        side_id: str = "",
        side_color: str = "#38bdf8",
        active: bool = True,
        movement_penalty: float = 1.0,
        detection_penalty: float = 0.0,
        communication_penalty: float = 0.0,
        affected_domains: Optional[list[str]] = None,
        description: str = "",
    ):
        self.id = id
        self.name = name
        self.class_name = class_name
        self.side_id = side_id
        self.latitude = latitude
        self.longitude = longitude
        self.altitude = altitude
        self.radius_nm = max(0.0, radius_nm)
        self.obstacle_type = obstacle_type
        self.side_color = side_color
        self.active = active
        self.movement_penalty = min(1.0, max(0.0, movement_penalty))
        self.detection_penalty = min(1.0, max(0.0, detection_penalty))
        self.communication_penalty = min(1.0, max(0.0, communication_penalty))
        self.affected_domains = affected_domains or ["aircraft", "ship"]
        self.description = description

    def to_dict(self):
        return self.__dict__
