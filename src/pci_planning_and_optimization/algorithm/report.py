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

from dataclasses import asdict, dataclass, field
from datetime import UTC, datetime

from pci_planning_and_optimization.algorithm.conflict_graph import (
    CLASS_COLLISION,
    CLASS_CONFUSION,
    CLASS_MOD3,
    CLASS_MOD4,
    CLASS_MOD6,
    CLASS_MOD30,
    AllConflicts,
    ConflictEdge,
    all_conflicts,
)
from pci_planning_and_optimization.models import Network, Technology

DEFAULT_CONFIDENCE_WEIGHTS: dict[str, float] = {
    CLASS_COLLISION: 1.0,
    CLASS_CONFUSION: 0.7,
    CLASS_MOD3: 0.4,
    CLASS_MOD4: 0.3,
    CLASS_MOD30: 0.3,
    CLASS_MOD6: 0.2,
}


@dataclass
class ClassSummary:

    name: str
    n_pairs: int = 0
    n_real: int = 0
    n_shadow: int = 0
    total_ho_attempts: int = 0
    total_ho_failures: int = 0

    @property
    def weighted_failure_rate(self) -> float:
        return (
            self.total_ho_failures / self.total_ho_attempts
            if self.total_ho_attempts else 0.0
        )

    def to_dict(self) -> dict[str, object]:
        return {
            "name": self.name,
            "n_pairs": self.n_pairs,
            "n_real": self.n_real,
            "n_shadow": self.n_shadow,
            "total_ho_attempts": self.total_ho_attempts,
            "total_ho_failures": self.total_ho_failures,
            "weighted_failure_rate": round(self.weighted_failure_rate, 5),
        }


@dataclass
class CellConflictSummary:

    cell_id: str
    pci: int
    technology: str
    n_collisions: int = 0
    n_confusions: int = 0
    n_mod3: int = 0
    n_mod4: int = 0
    n_mod6: int = 0
    n_mod30: int = 0
    total_ho_attempts: int = 0
    total_ho_failures: int = 0
    n_real_conflicts: int = 0
    n_shadow_conflicts: int = 0

    def to_dict(self) -> dict[str, object]:
        return asdict(self)


@dataclass
class ConflictReport:

    technology: str
    generated_at: str
    n_cells: int
    n_pairs_total: int
    n_pairs_real: int
    n_pairs_shadow: int

    class_summary: dict[str, ClassSummary] = field(default_factory=dict)
    nrt_real_conflicts: list[ConflictEdge] = field(default_factory=list)
    nrt_shadow_conflicts: list[ConflictEdge] = field(default_factory=list)
    top_impact: list[ConflictEdge] = field(default_factory=list)
    per_cell_summary: list[CellConflictSummary] = field(default_factory=list)
    predicted_ho_failures_avoided: float = 0.0
    confidence_weights: dict[str, float] = field(default_factory=dict)

    def to_dict(self) -> dict[str, object]:
        return {
            "technology": self.technology,
            "generated_at": self.generated_at,
            "n_cells": self.n_cells,
            "n_pairs_total": self.n_pairs_total,
            "n_pairs_real": self.n_pairs_real,
            "n_pairs_shadow": self.n_pairs_shadow,
            "class_summary": {
                k: v.to_dict() for k, v in self.class_summary.items()
            },
            "nrt_real_conflicts": [e.to_dict() for e in self.nrt_real_conflicts],
            "nrt_shadow_conflicts": [e.to_dict() for e in self.nrt_shadow_conflicts],
            "top_impact": [e.to_dict() for e in self.top_impact],
            "per_cell_summary": [c.to_dict() for c in self.per_cell_summary],
            "predicted_ho_failures_avoided": round(self.predicted_ho_failures_avoided, 1),
            "confidence_weights": self.confidence_weights,
        }


def _bump_cell(
    summary_map: dict[str, CellConflictSummary],
    network: Network,
    cell_id: str,
    edge: ConflictEdge,
    *,
    counter_field: str,
) -> None:
    if cell_id not in summary_map:
        cell = network.cells.get(cell_id)
        if cell is None:
            return
        summary_map[cell_id] = CellConflictSummary(
            cell_id=cell.id,
            pci=cell.pci,
            technology=cell.technology.value,
        )
    s = summary_map[cell_id]
    setattr(s, counter_field, getattr(s, counter_field) + 1)


def generate_conflict_report(
    network: Network,
    technology: Technology,
    *,
    enable_mod6_lte: bool = False,
    top_n: int = 20,
    confidence_weights: dict[str, float] | None = None,
) -> ConflictReport:
    weights = (
        dict(DEFAULT_CONFIDENCE_WEIGHTS)
        if confidence_weights is None
        else dict(confidence_weights)
    )

    bundle: AllConflicts = all_conflicts(
        network, technology, enable_mod6_lte=enable_mod6_lte
    )

    class_keys = [
        CLASS_COLLISION, CLASS_CONFUSION,
        CLASS_MOD3, CLASS_MOD4, CLASS_MOD30, CLASS_MOD6,
    ]
    class_summary: dict[str, ClassSummary] = {
        k: ClassSummary(name=k) for k in class_keys
    }

    def _absorb_into_class(klass: str, edges: list[ConflictEdge]) -> None:
        cs = class_summary[klass]
        for e in edges:
            cs.n_pairs += 1
            if e.relation_source == "real":
                cs.n_real += 1
            else:
                cs.n_shadow += 1
            cs.total_ho_attempts += e.ho_attempts
            cs.total_ho_failures += e.ho_failures

    _absorb_into_class(CLASS_COLLISION, bundle.collisions)
    _absorb_into_class(CLASS_CONFUSION, bundle.confusions)
    _absorb_into_class(CLASS_MOD3, bundle.mod3)
    _absorb_into_class(CLASS_MOD4, bundle.mod4)
    _absorb_into_class(CLASS_MOD30, bundle.mod30)
    _absorb_into_class(CLASS_MOD6, bundle.mod6)

    pair_to_edge: dict[tuple, ConflictEdge] = {}
    precedence = (
        CLASS_COLLISION, CLASS_CONFUSION,
        CLASS_MOD3, CLASS_MOD4, CLASS_MOD30, CLASS_MOD6,
    )
    precedence_index = {c: i for i, c in enumerate(precedence)}
    for edge_list in (
        bundle.collisions, bundle.confusions,
        bundle.mod3, bundle.mod4, bundle.mod30, bundle.mod6,
    ):
        for e in edge_list:
            key = (e.cell_a_id, e.cell_b_id)
            existing = pair_to_edge.get(key)
            if existing is None or precedence_index[e.conflict_class] < precedence_index[existing.conflict_class]:
                pair_to_edge[key] = e

    from pci_planning_and_optimization.algorithm.conflict_graph import _sort_conflicts
    real_conflicts = _sort_conflicts(
        [e for e in pair_to_edge.values() if e.relation_source == "real"]
    )
    shadow_conflicts = _sort_conflicts(
        [e for e in pair_to_edge.values() if e.relation_source == "shadow"]
    )

    cell_summaries: dict[str, CellConflictSummary] = {}
    counter_per_class = {
        CLASS_COLLISION: "n_collisions",
        CLASS_CONFUSION: "n_confusions",
        CLASS_MOD3: "n_mod3",
        CLASS_MOD4: "n_mod4",
        CLASS_MOD30: "n_mod30",
        CLASS_MOD6: "n_mod6",
    }
    for klass, edges in (
        (CLASS_COLLISION, bundle.collisions),
        (CLASS_CONFUSION, bundle.confusions),
        (CLASS_MOD3, bundle.mod3),
        (CLASS_MOD4, bundle.mod4),
        (CLASS_MOD30, bundle.mod30),
        (CLASS_MOD6, bundle.mod6),
    ):
        counter_field = counter_per_class[klass]
        for e in edges:
            _bump_cell(cell_summaries, network, e.cell_a_id, e, counter_field=counter_field)
            _bump_cell(cell_summaries, network, e.cell_b_id, e, counter_field=counter_field)

    for e in pair_to_edge.values():
        for cid in (e.cell_a_id, e.cell_b_id):
            s = cell_summaries.get(cid)
            if s is None:
                continue
            s.total_ho_attempts += e.ho_attempts
            s.total_ho_failures += e.ho_failures
            if e.relation_source == "real":
                s.n_real_conflicts += 1
            else:
                s.n_shadow_conflicts += 1

    per_cell = sorted(
        cell_summaries.values(),
        key=lambda s: (-s.total_ho_failures, s.cell_id),
    )

    top_impact = real_conflicts[:top_n]

    predicted = 0.0
    for e in real_conflicts:
        w = weights.get(e.conflict_class, 0.0)
        predicted += w * e.ho_failures

    return ConflictReport(
        technology=technology.value,
        generated_at=datetime.now(UTC).isoformat(timespec="seconds"),
        n_cells=sum(
            1 for c in network.cells.values() if c.technology == technology
        ),
        n_pairs_total=len(pair_to_edge),
        n_pairs_real=len(real_conflicts),
        n_pairs_shadow=len(shadow_conflicts),
        class_summary=class_summary,
        nrt_real_conflicts=real_conflicts,
        nrt_shadow_conflicts=shadow_conflicts,
        top_impact=top_impact,
        per_cell_summary=per_cell,
        predicted_ho_failures_avoided=predicted,
        confidence_weights=weights,
    )
