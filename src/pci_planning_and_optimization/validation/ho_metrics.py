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

    predicted_ho_failures_avoided_per_period: float
    projected_hosr_delta_pp_lower_bound: float

    def to_dict(self) -> dict[str, Any]:
        return {
            "technology": self.technology,
            "generated_at": self.generated_at,
            "skipped": self.skipped,
            "skip_reason": self.skip_reason,
            "n_cells": self.n_cells,
            "n_recommendations": self.n_recommendations,
            "churn_pct": round(self.churn_pct, 4),
            "before": self.before.to_dict(),
            "after": self.after.to_dict(),
            "palette_before": self.palette_before.to_dict(),
            "palette_after": self.palette_after.to_dict(),
            "reuse_distance_before": self.reuse_distance_before.to_dict(),
            "reuse_distance_after": self.reuse_distance_after.to_dict(),
            "predicted_ho_failures_avoided_per_period": round(
                self.predicted_ho_failures_avoided_per_period, 1
            ),
            "projected_hosr_delta_pp_lower_bound": round(
                self.projected_hosr_delta_pp_lower_bound, 3
            ),
        }


def _conflict_snapshot(
    network: Network, technology: Technology, *, enable_mod6_lte: bool
) -> ConflictSnapshot:
    bundle = all_conflicts(network, technology, enable_mod6_lte=enable_mod6_lte)
    return ConflictSnapshot(
        n_collisions=len(bundle.collisions),
        n_confusions=len(bundle.confusions),
        n_mod3=len(bundle.mod3),
        n_mod4=len(bundle.mod4),
        n_mod6=len(bundle.mod6),
        n_mod30=len(bundle.mod30),
    )


def _palette_stats(network: Network, technology: Technology) -> PaletteStats:
    pool_size = _pci_pool_size(technology)
    pcis = [c.pci for c in network.cells.values() if c.technology == technology]
    unique = set(pcis)
    counts = {0: 0, 1: 0, 2: 0}
    for p in pcis:
        counts[p % 3] += 1

    nonzero = [v for v in counts.values() if v > 0]
    if nonzero and min(nonzero) > 0:
        imbalance = max(counts.values()) / min(nonzero)
    else:
        imbalance = 1.0

    return PaletteStats(
        pool_size=pool_size,
        n_unique_pcis=len(unique),
        utilization_pct=100.0 * len(unique) / pool_size if pool_size else 0.0,
        mod3_class_counts=counts,
        mod3_imbalance=imbalance,
    )


def _reuse_distance_stats(
    network: Network, technology: Technology
) -> ReuseDistanceStats:
    cells_by_pci: dict[int, list[Any]] = {}
    for c in network.cells.values():
        if c.technology != technology:
            continue
        if c.lat is None or c.lon is None:
            continue
        cells_by_pci.setdefault(c.pci, []).append(c)

    min_distances: list[float] = []
    for pci, cells in cells_by_pci.items():
        if len(cells) < 2:
            continue
        local_min = float("inf")
        for i, ci in enumerate(cells):
            for cj in cells[i + 1:]:
                d = _haversine_m(ci.lat, ci.lon, cj.lat, cj.lon)
                if d < local_min:
                    local_min = d
        if local_min < float("inf"):
            min_distances.append(local_min)

    if not min_distances:
        return ReuseDistanceStats()

    sorted_d = sorted(min_distances)
    p10_idx = max(0, int(len(sorted_d) * 0.10) - 1)
    return ReuseDistanceStats(
        n_reused_pcis=len(min_distances),
        min_distance_m=sorted_d[0],
        median_distance_m=statistics.median(sorted_d),
        p10_distance_m=sorted_d[p10_idx],
    )


def _apply_recommendations(
    base_network: Network,
    recommendations: list[dict[str, Any]],
    technology: Technology,
) -> Network:
    after = deepcopy(base_network)
    for rec in recommendations:
        if rec.get("technology") != technology.value:
            continue
        cell_id = rec["cell_id"]
        cell = after.cells.get(cell_id)
        if cell is None:
            continue
        new_pci = int(rec["pci_new"])
        cell.pci = new_pci
        if cell.technology == Technology.LTE:
            cell.pci_components = (new_pci // 3, new_pci % 3)
    return after


def compute_ho_validation(
    before_network: Network,
    technology: Technology,
    *,
    recommendations: Iterable[dict[str, Any]],
    skipped: bool = False,
    skip_reason: str | None = None,
    enable_mod6_lte: bool = False,
) -> HoValidationReport:
    n_cells = sum(
        1 for c in before_network.cells.values() if c.technology == technology
    )

    if skipped or n_cells == 0:
        empty = ConflictSnapshot()
        empty_palette = PaletteStats(
            pool_size=_pci_pool_size(technology),
            n_unique_pcis=0,
            utilization_pct=0.0,
        )
        empty_reuse = ReuseDistanceStats()
        return HoValidationReport(
            technology=technology.value,
            generated_at=datetime.now(UTC).isoformat(timespec="seconds"),
            skipped=True,
            skip_reason=skip_reason or (
                f"No cells of technology={technology.value} in input"
                if n_cells == 0 else "Skipped"
            ),
            n_cells=n_cells,
            n_recommendations=0,
            churn_pct=0.0,
            before=empty,
            after=empty,
            palette_before=empty_palette,
            palette_after=empty_palette,
            reuse_distance_before=empty_reuse,
            reuse_distance_after=empty_reuse,
            predicted_ho_failures_avoided_per_period=0.0,
            projected_hosr_delta_pp_lower_bound=0.0,
        )

    tech_recs: list[dict[str, Any]] = [
        r for r in recommendations if r.get("technology") == technology.value
    ]

    before_snapshot = _conflict_snapshot(
        before_network, technology, enable_mod6_lte=enable_mod6_lte
    )
    palette_before = _palette_stats(before_network, technology)
    reuse_before = _reuse_distance_stats(before_network, technology)

    after_network = _apply_recommendations(before_network, tech_recs, technology)
    after_snapshot = _conflict_snapshot(
        after_network, technology, enable_mod6_lte=enable_mod6_lte
    )
    palette_after = _palette_stats(after_network, technology)
    reuse_after = _reuse_distance_stats(after_network, technology)

    predicted_ho_avoided = sum(
        float(r.get("predicted_ho_failures_avoided_per_period", 0.0))
        for r in tech_recs
    )

    total_attempts = sum(
        c.ho_attempts_total
        for c in before_network.cells.values()
        if c.technology == technology and c.ho_attempts_total > 0
    )
    total_successes = sum(
        c.ho_successes_total
        for c in before_network.cells.values()
        if c.technology == technology
    )
    if total_attempts > 0:
        baseline_hosr = 100.0 * total_successes / total_attempts
        projected_hosr = (
            100.0 * (total_successes + predicted_ho_avoided) / total_attempts
        )
        hosr_delta = max(0.0, projected_hosr - baseline_hosr)
    else:
        hosr_delta = 0.0

    churn_pct = 100.0 * len(tech_recs) / n_cells if n_cells else 0.0

    return HoValidationReport(
        technology=technology.value,
        generated_at=datetime.now(UTC).isoformat(timespec="seconds"),
        skipped=False,
        skip_reason=None,
        n_cells=n_cells,
        n_recommendations=len(tech_recs),
        churn_pct=churn_pct,
        before=before_snapshot,
        after=after_snapshot,
        palette_before=palette_before,
        palette_after=palette_after,
        reuse_distance_before=reuse_before,
        reuse_distance_after=reuse_after,
        predicted_ho_failures_avoided_per_period=predicted_ho_avoided,
        projected_hosr_delta_pp_lower_bound=hosr_delta,
    )
