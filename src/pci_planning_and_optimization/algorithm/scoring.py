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

from typing import Any, Protocol

from pci_planning_and_optimization.app_config import (
    LteScoringConfig,
    NrScoringConfig,
    ScoringConfig,
)
from pci_planning_and_optimization.models import Cell, Network, Technology


class WeightProvider(Protocol):

    def weight(self, a: Cell, b: Cell) -> float: ...


_MOD_NAME_TO_INT = {"mod3": 3, "mod4": 4, "mod6": 6, "mod30": 30}

COLLISION_PENALTY = 10.0

CONFUSION_PENALTY = 6.0


def _resolved_mod_priority(scoring_cfg: ScoringConfig, tech: Technology) -> list[int]:
    if tech == Technology.LTE:
        cfg: LteScoringConfig = scoring_cfg.lte
        out: list[int] = []
        for name in cfg.mod_priority:
            if name == "mod6" and not cfg.enable_mod6:
                continue
            out.append(_MOD_NAME_TO_INT[name])
        return out
    nr_cfg: NrScoringConfig = scoring_cfg.nr
    return [_MOD_NAME_TO_INT[name] for name in nr_cfg.mod_priority]


def _mod_penalty(
    candidate_pci: int,
    neighbors: list[Cell],
    cell: Cell,
    n: int,
    weight_provider: WeightProvider,
) -> float:
    total = 0.0
    for u in neighbors:
        if (candidate_pci % n) == (u.pci % n):
            total += weight_provider.weight(cell, u)
    return total


def candidate_sort_key(
    network: Network,
    cell: Cell,
    candidate_pci: int,
    scoring_cfg: ScoringConfig,
    weight_provider: WeightProvider,
    *,
    neighbors: list[Cell] | None = None,
) -> tuple[float, ...]:
    if neighbors is None:
        neighbors = network.neighbors_of(cell.id, same_tech_only=True)

    same_freq_neighbors = [
        n for n in neighbors
        if n.primary_frequency() == cell.primary_frequency()
        and cell.primary_frequency() is not None
    ]

    mods = _resolved_mod_priority(scoring_cfg, cell.technology)
    mod_terms = tuple(
        _mod_penalty(candidate_pci, same_freq_neighbors, cell, n, weight_provider)
        for n in mods
    )

    if same_freq_neighbors:
        max_distance = max(abs(candidate_pci - u.pci) for u in same_freq_neighbors)
    else:
        max_distance = 0

    return (*mod_terms, -max_distance, candidate_pci)


def compute_total_soft_cost(
    network: Network,
    technology: Technology,
    weight_provider: WeightProvider,
    scoring_cfg: ScoringConfig,
) -> float:
    mods = _resolved_mod_priority(scoring_cfg, technology)
    if not mods:
        return 0.0

    total = 0.0

    seen: set = set()
    for r in network.relations:
        if r.cross_technology:
            continue
        a = network.cells.get(r.source_cell_id)
        b = network.cells.get(r.target_cell_id)
        if a is None or b is None:
            continue
        if a.technology != technology or b.technology != technology:
            continue
        if a.id == b.id:
            continue
        if a.primary_frequency() != b.primary_frequency():
            continue
        if a.primary_frequency() is None:
            continue
        x_id, y_id = (a.id, b.id) if a.id < b.id else (b.id, a.id)
        key = (x_id, y_id)
        if key in seen:
            continue
        seen.add(key)
        x = network.cells[x_id]
        y = network.cells[y_id]
        w = weight_provider.weight(x, y)
        if w == 0.0:
            continue

        if x.pci == y.pci:
            total += w * COLLISION_PENALTY
            continue
        for n in mods:
            if (x.pci % n) == (y.pci % n):
                total += w
    return total + _confusion_cost(network, technology, weight_provider)


def _confusion_cost(
    network: Network,
    technology: Technology,
    weight_provider: WeightProvider,
) -> float:
    from pci_planning_and_optimization.algorithm.conflict_graph import _real_neighbor_map

    total = 0.0
    for source_id, neighbor_ids in _real_neighbor_map(network).items():
        source = network.cells.get(source_id)
        if source is None or source.technology != technology:
            continue
        by_pci: dict[tuple[int, Any], list[Cell]] = {}
        for nid in neighbor_ids:
            n = network.cells.get(nid)
            if n is None or n.technology != technology:
                continue
            freq = n.primary_frequency()
            if freq is None:
                continue
            by_pci.setdefault((n.pci, freq), []).append(n)
        for group in by_pci.values():
            if len(group) < 2:
                continue
            for i, a in enumerate(group):
                for b in group[i + 1:]:
                    w = weight_provider.weight(a, b) or weight_provider.weight(source, a)
                    total += (w or 0.0) * CONFUSION_PENALTY
    return total
