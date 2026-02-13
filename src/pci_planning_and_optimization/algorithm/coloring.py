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

import logging
from dataclasses import asdict, dataclass, field
from datetime import UTC, datetime

from pci_planning_and_optimization.algorithm.conflict_graph import (
    AllConflicts,
    all_conflicts,
)
from pci_planning_and_optimization.algorithm.scoring import (
    WeightProvider,
    candidate_sort_key,
    compute_total_soft_cost,
)
from pci_planning_and_optimization.app_config import AppConfig
from pci_planning_and_optimization.models import Cell, Network, Technology
from pci_planning_and_optimization.weighting.policy import OperatorPolicy

_log = logging.getLogger(__name__)


REASON_COLLISION = "PCI_COLLISION_RESOLUTION"
REASON_CONFUSION = "PCI_CONFUSION_RESOLUTION"
REASON_MODN = "MODN_INTERFERENCE_REDUCTION"


def default_weight_provider(network: Network) -> WeightProvider:
    from pci_planning_and_optimization.weighting.distance import EuclideanDistanceProvider
    from pci_planning_and_optimization.weighting.handover import HoFailureRateProvider
    from pci_planning_and_optimization.weighting.handover_fallback import (
        CellLevelHoFallback,
    )

    if any(r.ho_failures for r in network.relations):
        return HoFailureRateProvider(network=network)

    has_pair_attempts = any(r.ho_attempts for r in network.relations)
    has_cell_totals = any(c.ho_attempts_total for c in network.cells.values())
    if has_pair_attempts and has_cell_totals:
        _log.info(
            "per-pair HO failure counters absent — inferring edge weights from "
            "cell-level totals by proportional attribution"
        )
        return CellLevelHoFallback(network=network)

    _log.info(
        "no HO counters in this network — weighting edges by distance/RF "
        "overlap instead (mod-N ordering and the revert guard need a "
        "non-zero weight to function)"
    )
    return EuclideanDistanceProvider()


@dataclass
class ChangeRecommendation:

    cell_id: str
    technology: str
    mo_class: str

    pci_old: int
    pci_new: int
    pci_components_new: tuple[int, int] | None

    reason_code: str
    reason_text: str

    sort_key_old: tuple[float, ...]
    sort_key_new: tuple[float, ...]

    predicted_ho_failures_avoided_per_week: float

    pass_number: int
    locked_neighborhood: list[str]

    def to_dict(self) -> dict[str, object]:
        d = asdict(self)
        d["sort_key_old"] = list(self.sort_key_old)
        d["sort_key_new"] = list(self.sort_key_new)
        if self.pci_components_new is not None:
            d["pci_components_new"] = {
                "group": self.pci_components_new[0],
                "sub": self.pci_components_new[1],
            }
        d["predicted_ho_failures_avoided_per_week"] = round(
            self.predicted_ho_failures_avoided_per_week, 1
        )
        return d


@dataclass
class PassSummary:
    pass_number: int
    n_changes: int
    soft_cost_before: float
    soft_cost_after: float
    improvement: float
    stopped_reason: str

    def to_dict(self) -> dict[str, object]:
        return {
            "pass_number": self.pass_number,
            "n_changes": self.n_changes,
            "soft_cost_before": round(self.soft_cost_before, 5),
            "soft_cost_after": round(self.soft_cost_after, 5),
            "improvement": round(self.improvement, 5),
            "stopped_reason": self.stopped_reason,
        }


@dataclass
class OptimizationRun:
    technology: str
    generated_at: str
    n_cells: int
    n_pairs_evaluated: int

    passes_executed: int
    converged: bool
    final_soft_cost: float

    changes: list[ChangeRecommendation] = field(default_factory=list)
    pass_history: list[PassSummary] = field(default_factory=list)

    config_snapshot: dict[str, object] = field(default_factory=dict)

    def to_dict(self) -> dict[str, object]:
        return {
            "technology": self.technology,
            "generated_at": self.generated_at,
            "n_cells": self.n_cells,
            "n_pairs_evaluated": self.n_pairs_evaluated,
            "passes_executed": self.passes_executed,
            "converged": self.converged,
            "final_soft_cost": round(self.final_soft_cost, 5),
            "changes": [c.to_dict() for c in self.changes],
            "pass_history": [ps.to_dict() for ps in self.pass_history],
            "config_snapshot": self.config_snapshot,
        }


def pick_pci(
    cell: Cell,
    allowed_pool: set[int],
    network: Network,
    scoring_cfg,
    weight_provider: WeightProvider,
) -> tuple[int, tuple[float, ...]] | None:
    if not allowed_pool:
        return None

    neighbors = network.neighbors_of(cell.id, same_tech_only=True)

    best_pci: int | None = None
    best_key: tuple[float, ...] | None = None

    for cand in allowed_pool:
        key = candidate_sort_key(
            network, cell, cand, scoring_cfg, weight_provider, neighbors=neighbors
        )
        if best_key is None or key < best_key:
            best_key = key
            best_pci = cand

    assert best_pci is not None and best_key is not None
    return best_pci, best_key


def _cells_to_consider(
    network: Network,
    technology: Technology,
    bundle: AllConflicts,
) -> list[Cell]:
    tier1_ids: set[str] = set()
    for edge in bundle.collisions:
        tier1_ids.add(edge.cell_a_id)
        tier1_ids.add(edge.cell_b_id)
    for edge in bundle.confusions:
        tier1_ids.add(edge.cell_a_id)
        tier1_ids.add(edge.cell_b_id)

    cell_ho_impact: dict[str, int] = {}
    for edge_list in (bundle.mod3, bundle.mod4, bundle.mod30, bundle.mod6):
        for edge in edge_list:
            for cid in (edge.cell_a_id, edge.cell_b_id):
                cell_ho_impact[cid] = cell_ho_impact.get(cid, 0) + edge.ho_failures

    tier2_ids = set(cell_ho_impact.keys()) - tier1_ids

    def t1_priority(cell_id: str) -> tuple[float, str]:
        cell = network.cells[cell_id]
        prb = cell.prb_util if cell.prb_util is not None else 0.0
        impact = cell_ho_impact.get(cell_id, 0)
        return (-prb * impact, cell_id)

    def t2_priority(cell_id: str) -> tuple[float, str]:
        cell = network.cells[cell_id]
        prb = cell.prb_util if cell.prb_util is not None else 0.0
        return (-prb * cell_ho_impact.get(cell_id, 0), cell_id)

    tier1_sorted = sorted(tier1_ids, key=t1_priority)
    tier2_sorted = sorted(tier2_ids, key=t2_priority)

    out: list[Cell] = []
    for cid in tier1_sorted:
        if cid in network.cells and network.cells[cid].technology == technology:
            out.append(network.cells[cid])
    for cid in tier2_sorted:
        if cid in network.cells and network.cells[cid].technology == technology:
            out.append(network.cells[cid])
    return out


def _lock_neighborhood(
    network: Network, cell_id: str, locked: set[str]
) -> list[str]:
    newly = [cell_id]
    locked.add(cell_id)
    for nid in network.n_hop_neighborhood(cell_id, n=2, same_tech_only=True):
        if nid not in locked:
            newly.append(nid)
            locked.add(nid)
    return newly


