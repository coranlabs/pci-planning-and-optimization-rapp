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

import statistics
from collections.abc import Iterable
from copy import deepcopy
from dataclasses import asdict, dataclass, field
from datetime import UTC, datetime
from math import asin, cos, radians, sin, sqrt
from typing import Any

from pci_planning_and_optimization.algorithm.conflict_graph import (
    all_conflicts,
)
from pci_planning_and_optimization.models import Network, Technology


def _haversine_m(lat1: float, lon1: float, lat2: float, lon2: float) -> float:
    earth_r = 6_371_008.8
    phi1, phi2 = radians(lat1), radians(lat2)
    dphi = radians(lat2 - lat1)
    dlam = radians(lon2 - lon1)
    a = sin(dphi / 2) ** 2 + cos(phi1) * cos(phi2) * sin(dlam / 2) ** 2
    return 2 * earth_r * asin(sqrt(a))


def _pci_pool_size(tech: Technology) -> int:
    return 504 if tech == Technology.LTE else 1008


@dataclass
class ConflictSnapshot:

    n_collisions: int = 0
    n_confusions: int = 0
    n_mod3: int = 0
    n_mod4: int = 0
    n_mod6: int = 0
    n_mod30: int = 0

    def to_dict(self) -> dict[str, int]:
        return asdict(self)


@dataclass
class PaletteStats:

    pool_size: int
    n_unique_pcis: int
    utilization_pct: float
    mod3_class_counts: dict[int, int] = field(
        default_factory=lambda: {0: 0, 1: 0, 2: 0}
    )
    mod3_imbalance: float = 1.0

    def to_dict(self) -> dict[str, Any]:
        return {
            "pool_size": self.pool_size,
            "n_unique_pcis": self.n_unique_pcis,
            "utilization_pct": round(self.utilization_pct, 2),
            "mod3_class_counts": dict(self.mod3_class_counts),
            "mod3_imbalance": round(self.mod3_imbalance, 3),
        }


@dataclass
class ReuseDistanceStats:

    n_reused_pcis: int = 0
    min_distance_m: float | None = None
    median_distance_m: float | None = None
    p10_distance_m: float | None = None

    def to_dict(self) -> dict[str, Any]:
        return {
            "n_reused_pcis": self.n_reused_pcis,
            "min_distance_m": round(self.min_distance_m, 1) if self.min_distance_m else None,
            "median_distance_m": round(self.median_distance_m, 1) if self.median_distance_m else None,
            "p10_distance_m": round(self.p10_distance_m, 1) if self.p10_distance_m else None,
        }


@dataclass
class HoValidationReport:

    technology: str
    generated_at: str
    skipped: bool
    skip_reason: str | None

    n_cells: int
    n_recommendations: int
    churn_pct: float

    before: ConflictSnapshot
    after: ConflictSnapshot

    palette_before: PaletteStats
    palette_after: PaletteStats

    reuse_distance_before: ReuseDistanceStats
    reuse_distance_after: ReuseDistanceStats

    predicted_ho_failures_avoided_per_week: float
    projected_hosr_delta_pp_lower_bound: float

