# Copyright 2025-2026 coRAN LABS Private Limited
#
# Licensed under the Apache License, Version 2.0 (the "License");
# you may not use this file except in compliance with the License.
# You may obtain a copy of the License at
#
#     http://www.apache.org/licenses/LICENSE-2.0
#
# Unless required by applicable law or agreed to in writing, software
# distributed under the License is distributed on an "AS IS" BASIS,
# WITHOUT WARRANTIES OR CONDITIONS OF ANY KIND, either express or implied.
# See the License for the specific language governing permissions and
# limitations under the License.

from __future__ import annotations

from dataclasses import dataclass
from math import asin, cos, exp, pi, radians, sin, sqrt

from pci_planning_and_optimization.models import Cell
from pci_planning_and_optimization.weighting.base import WeightProvider

DEFAULT_HALF_DISTANCE_M = 600.0
DEFAULT_AZIMUTH_FLOOR = 0.2


def _haversine_m(lat1: float, lon1: float, lat2: float, lon2: float) -> float:
    earth_r = 6_371_008.8
    phi1, phi2 = radians(lat1), radians(lat2)
    dphi = radians(lat2 - lat1)
    dlam = radians(lon2 - lon1)
    a = sin(dphi / 2) ** 2 + cos(phi1) * cos(phi2) * sin(dlam / 2) ** 2
    return 2 * earth_r * asin(sqrt(a))


def _bearing_deg(lat1: float, lon1: float, lat2: float, lon2: float) -> float:
    phi1, phi2 = radians(lat1), radians(lat2)
    dlam = radians(lon2 - lon1)
    x = sin(dlam) * cos(phi2)
    y = cos(phi1) * sin(phi2) - sin(phi1) * cos(phi2) * cos(dlam)
    bearing = (180.0 / pi) * (
        __import__("math").atan2(x, y)
    )
    return (bearing + 360.0) % 360.0


def _azimuth_alignment(a: Cell, b: Cell) -> float:
    if a.azimuth is None or b.azimuth is None:
        return 1.0
    if a.lat is None or a.lon is None or b.lat is None or b.lon is None:
        return 1.0
    bearing_ab = _bearing_deg(a.lat, a.lon, b.lat, b.lon)
    bearing_ba = (bearing_ab + 180.0) % 360.0
    da = abs(((bearing_ab - a.azimuth) + 540.0) % 360.0 - 180.0)
    db = abs(((bearing_ba - b.azimuth) + 540.0) % 360.0 - 180.0)
    avg_misalignment = (da + db) / 2.0
    fraction = avg_misalignment / 180.0
    return 1.0 - fraction * (1.0 - DEFAULT_AZIMUTH_FLOOR)


@dataclass
class EuclideanDistanceProvider(WeightProvider):

    half_distance_m: float = DEFAULT_HALF_DISTANCE_M
    azimuth_aware: bool = True

    def weight(self, a: Cell, b: Cell) -> float:
        if a.lat is None or a.lon is None or b.lat is None or b.lon is None:
            return 0.0
        d = _haversine_m(a.lat, a.lon, b.lat, b.lon)
        decay = exp(-d * 0.6931471805599453 / self.half_distance_m)
        if not self.azimuth_aware:
            return decay
        return decay * _azimuth_alignment(a, b)
