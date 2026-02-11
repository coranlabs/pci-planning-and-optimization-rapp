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
from math import asin, cos, radians, sin, sqrt

import networkx as nx

from pci_planning_and_optimization.app_config import AppConfig
from pci_planning_and_optimization.models import (
    Cell,
    Network,
    RelationSource,
    Technology,
)

_log = logging.getLogger(__name__)


CLASS_COLLISION = "collision"
CLASS_CONFUSION = "confusion"
CLASS_MOD3 = "mod3"
CLASS_MOD4 = "mod4"
CLASS_MOD6 = "mod6"
CLASS_MOD30 = "mod30"

_CLASS_PRECEDENCE = (
    CLASS_COLLISION,
    CLASS_CONFUSION,
    CLASS_MOD3,
    CLASS_MOD4,
    CLASS_MOD30,
    CLASS_MOD6,
)


@dataclass(frozen=False)
class ConflictEdge:

    cell_a_id: str
    cell_b_id: str
    pci_a: int
    pci_b: int
    technology: str
    conflict_class: str
    ho_attempts: int
    ho_failures: int
    ho_failure_rate: float
    relation_source: str
    frequency: int | None
    distance_m: float | None = None

    def to_dict(self) -> dict[str, object]:
        d = asdict(self)
        if d["ho_failure_rate"] is not None:
            d["ho_failure_rate"] = round(d["ho_failure_rate"], 5)
        if d["distance_m"] is not None:
            d["distance_m"] = round(d["distance_m"], 1)
        return d


def _haversine_m(lat1: float, lon1: float, lat2: float, lon2: float) -> float:
    earth_r = 6_371_008.8
    phi1, phi2 = radians(lat1), radians(lat2)
    dphi = radians(lat2 - lat1)
    dlam = radians(lon2 - lon1)
    a = sin(dphi / 2) ** 2 + cos(phi1) * cos(phi2) * sin(dlam / 2) ** 2
    return 2 * earth_r * asin(sqrt(a))


def _pair_distance(a: Cell, b: Cell) -> float | None:
    if a.lat is None or a.lon is None or b.lat is None or b.lon is None:
        return None
    return _haversine_m(a.lat, a.lon, b.lat, b.lon)


def _canonical_pair(a_id: str, b_id: str) -> tuple[str, str]:
    return (a_id, b_id) if a_id < b_id else (b_id, a_id)


def _real_neighbor_map(network: Network) -> dict[str, set[str]]:
    out: dict[str, set[str]] = {}
    for r in network.relations:
        if r.relation_source != RelationSource.REAL:
            continue
        out.setdefault(r.source_cell_id, set()).add(r.target_cell_id)
        out.setdefault(r.target_cell_id, set()).add(r.source_cell_id)
    return out


def _real_neighbor_ids(network: Network, cell_id: str) -> set[str]:
    return _real_neighbor_map(network).get(cell_id, set())


def _iter_intra_tech_pairs(
    network: Network, technology: Technology
) -> list[tuple[Cell, Cell, str]]:
    seen: set[tuple[str, str]] = set()
    pair_has_real: dict[tuple[str, str], bool] = {}
    pairs: list[tuple[Cell, Cell, str]] = []

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

        x_id, y_id = _canonical_pair(a.id, b.id)
        key = (x_id, y_id)
        is_real = (r.relation_source == RelationSource.REAL)
        pair_has_real[key] = pair_has_real.get(key, False) or is_real
        if key in seen:
            continue
        seen.add(key)
        x = network.cells[x_id]
        y = network.cells[y_id]
        pairs.append((x, y, "real" if is_real else "shadow"))

    fixed: list[tuple[Cell, Cell, str]] = []
    for x, y, _provisional in pairs:
        key = (x.id, y.id)
        fixed.append((x, y, "real" if pair_has_real[key] else "shadow"))
    return fixed


def _build_edge(
    network: Network,
    a: Cell,
    b: Cell,
    *,
    relation_source: str,
    conflict_class: str,
) -> ConflictEdge:
    assert a.id < b.id, "_build_edge expects canonical (a < b) ordering"
    attempts = network.ho_attempts_pair(a.id, b.id)
    fwd = network.relation(a.id, b.id)
    rev = network.relation(b.id, a.id)
    failures = (fwd.ho_failures if fwd else 0) + (rev.ho_failures if rev else 0)
    rate = failures / attempts if attempts else 0.0
    return ConflictEdge(
        cell_a_id=a.id,
        cell_b_id=b.id,
        pci_a=a.pci,
        pci_b=b.pci,
        technology=a.technology.value,
        conflict_class=conflict_class,
        ho_attempts=attempts,
        ho_failures=failures,
        ho_failure_rate=rate,
        relation_source=relation_source,
        frequency=a.primary_frequency(),
        distance_m=_pair_distance(a, b),
    )


def _sort_conflicts(conflicts: list[ConflictEdge]) -> list[ConflictEdge]:
    def key(e: ConflictEdge) -> tuple[int, int, int, float, str, str]:
        return (
            -e.ho_failures,
            -e.ho_attempts,
            0 if e.relation_source == "real" else 1,
            e.distance_m if e.distance_m is not None else float("inf"),
            e.cell_a_id,
            e.cell_b_id,
        )

    return sorted(conflicts, key=key)


def detect_collisions(network: Network, technology: Technology) -> list[ConflictEdge]:
    conflicts: list[ConflictEdge] = []
    for a, b, source in _iter_intra_tech_pairs(network, technology):
        if a.pci != b.pci:
            continue
        conflicts.append(_build_edge(
            network, a, b, relation_source=source, conflict_class=CLASS_COLLISION,
        ))
    return _sort_conflicts(conflicts)


def detect_confusions(network: Network, technology: Technology) -> list[ConflictEdge]:
    conflicts: list[ConflictEdge] = []
    real_neighbors = _real_neighbor_map(network)
    for a, b, source in _iter_intra_tech_pairs(network, technology):
        if a.pci == b.pci:
            continue

        is_confusion = False
        for source_cell, target in ((a, b), (b, a)):
            for nb_id in real_neighbors.get(source_cell.id, ()):
                if nb_id == target.id:
                    continue
                nb = network.cells.get(nb_id)
                if nb is None or nb.technology != technology:
                    continue
                if nb.pci != target.pci:
                    continue
                if nb.primary_frequency() != target.primary_frequency():
                    continue
                is_confusion = True
                break
            if is_confusion:
                break

        if not is_confusion:
            continue
        conflicts.append(_build_edge(
            network, a, b, relation_source=source, conflict_class=CLASS_CONFUSION,
        ))
    return _sort_conflicts(conflicts)


def compute_modN_violations(
    network: Network, technology: Technology, n: int
) -> list[ConflictEdge]:
    if n <= 0:
        raise ValueError(f"compute_modN_violations: n must be positive, got {n}")
    label = f"mod{n}"

    conflicts: list[ConflictEdge] = []
    for a, b, source in _iter_intra_tech_pairs(network, technology):
        if (a.pci % n) != (b.pci % n):
            continue
        conflicts.append(_build_edge(
            network, a, b, relation_source=source, conflict_class=label,
        ))
    return _sort_conflicts(conflicts)


def prepare_network(network: Network, config: AppConfig) -> Network:
    if not config.shadow_nrt.enabled:
        _log.info("shadow_nrt.enabled=false — skipping shadow-NRT injection")
        return network

    thresholds = {
        "macro_macro": float(config.shadow_nrt.distance_thresholds_m.macro_macro),
        "macro_small": float(config.shadow_nrt.distance_thresholds_m.macro_small),
        "small_small": float(config.shadow_nrt.distance_thresholds_m.small_small),
        "indoor_any": float(config.shadow_nrt.distance_thresholds_m.indoor_any),
    }
    added = network.add_shadow_relations(thresholds)
    _log.info(
        "shadow-NRT: added %d directed rows (%.0f logical pairs)",
        added, added / 2 if added else 0,
    )
    return network


def _modN_list_for_technology(
    technology: Technology, *, enable_mod6_lte: bool
) -> list[int]:
    if technology == Technology.NR:
        return [3, 4, 30]
    return [3, 30, 6] if enable_mod6_lte else [3, 30]


def build_g_squared(
    network: Network,
    technology: Technology,
    *,
    enable_mod6_lte: bool = False,
) -> nx.Graph:
    sub_lte, sub_nr = network.split_by_technology()
    sub = sub_lte if technology == Technology.LTE else sub_nr

    g = nx.Graph()
    for cell in sub.cells.values():
        g.add_node(cell.id, cell=cell)

    pair_to_edge: dict[tuple[str, str], ConflictEdge] = {}

    def _maybe_add(edge: ConflictEdge) -> None:
        key = (edge.cell_a_id, edge.cell_b_id)
        existing = pair_to_edge.get(key)
        if existing is None:
            pair_to_edge[key] = edge
            return
        if _CLASS_PRECEDENCE.index(edge.conflict_class) < _CLASS_PRECEDENCE.index(existing.conflict_class):
            pair_to_edge[key] = edge

    for edge in detect_collisions(sub, technology):
        _maybe_add(edge)
    for edge in detect_confusions(sub, technology):
        _maybe_add(edge)
    for n in _modN_list_for_technology(technology, enable_mod6_lte=enable_mod6_lte):
        for edge in compute_modN_violations(sub, technology, n):
            _maybe_add(edge)

    for edge in pair_to_edge.values():
        g.add_edge(
            edge.cell_a_id,
            edge.cell_b_id,
            conflict_class=edge.conflict_class,
            relation_source=edge.relation_source,
            ho_attempts=edge.ho_attempts,
            ho_failures=edge.ho_failures,
            ho_failure_rate=edge.ho_failure_rate,
            frequency=edge.frequency,
            distance_m=edge.distance_m,
            pci_a=edge.pci_a,
            pci_b=edge.pci_b,
        )

    return g


@dataclass
class AllConflicts:

    technology: str
    collisions: list[ConflictEdge] = field(default_factory=list)
    confusions: list[ConflictEdge] = field(default_factory=list)
    mod3: list[ConflictEdge] = field(default_factory=list)
    mod4: list[ConflictEdge] = field(default_factory=list)
    mod6: list[ConflictEdge] = field(default_factory=list)
    mod30: list[ConflictEdge] = field(default_factory=list)


def all_conflicts(
    network: Network,
    technology: Technology,
    *,
    enable_mod6_lte: bool = False,
) -> AllConflicts:
    out = AllConflicts(technology=technology.value)
    out.collisions = detect_collisions(network, technology)
    out.confusions = detect_confusions(network, technology)
    out.mod3 = compute_modN_violations(network, technology, 3)
    if technology == Technology.NR:
        out.mod4 = compute_modN_violations(network, technology, 4)
    elif enable_mod6_lte:
        out.mod6 = compute_modN_violations(network, technology, 6)
    out.mod30 = compute_modN_violations(network, technology, 30)
    return out
