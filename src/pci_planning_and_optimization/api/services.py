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

import hashlib
import json
import logging
import math
from pathlib import Path
from typing import Any

from pci_planning_and_optimization.algorithm.conflict_graph import (
    CLASS_COLLISION,
    CLASS_CONFUSION,
    all_conflicts,
)
from pci_planning_and_optimization.app_config import AppConfig
from pci_planning_and_optimization.models import Network, Technology

_log = logging.getLogger("pci_planning_and_optimization.api.services")


_CENTER_LAT = 53.3500
_CENTER_LON = -6.4200
_CLUSTER_RADIUS_KM = 11.0
_KM_PER_DEG_LAT = 110.574
_SECTOR_OFFSET_KM = 0.03


def synthesize_coords(cell_id: str) -> tuple[float, float]:
    site, _, sector = cell_id.rpartition("-")
    if not site:
        site, sector = cell_id, ""
    h = hashlib.md5(site.encode("utf-8"), usedforsecurity=False).digest()
    r_norm = int.from_bytes(h[:4], "big") / 0xFFFFFFFF
    theta = int.from_bytes(h[4:8], "big") / 0xFFFFFFFF * 2 * math.pi
    radius_km = math.sqrt(r_norm) * _CLUSTER_RADIUS_KM
    km_per_deg_lon = 111.320 * math.cos(math.radians(_CENTER_LAT))
    dlat = radius_km * math.cos(theta) / _KM_PER_DEG_LAT
    dlon = radius_km * math.sin(theta) / km_per_deg_lon

    idx = int(sector) if sector.isdigit() else (h[8] % 3 if sector else 0)
    bearing = math.radians(idx * 120.0)
    dlat += (_SECTOR_OFFSET_KM * math.cos(bearing)) / _KM_PER_DEG_LAT
    dlon += (_SECTOR_OFFSET_KM * math.sin(bearing)) / km_per_deg_lon
    return _CENTER_LAT + dlat, _CENTER_LON + dlon


def compute_kpis(network: Network | None) -> dict[str, Any]:
    if network is None:
        return {
            "active_cells": 0,
            "active_cells_delta_pct": None,
            "ho_success_rate": None,
            "ho_success_rate_delta_pct": None,
            "active_conflicts": 0,
            "active_conflicts_delta_abs": None,
            "pending_decisions": 0,
            "by_technology": {"lte": {"cells": 0}, "nr": {"cells": 0}},
        }

    cells = list(network.cells.values())
    lte_cells = [c for c in cells if c.technology == Technology.LTE]
    nr_cells = [c for c in cells if c.technology == Technology.NR]

    total_attempts = sum(c.ho_attempts_total for c in cells)
    total_successes = sum(c.ho_successes_total for c in cells)

    if total_attempts == 0 and network.relations:
        seen_pairs: set = set()
        rel_attempts = 0
        rel_failures = 0
        for r in network.relations:
            a, b = sorted([r.source_cell_id, r.target_cell_id])
            if (a, b) in seen_pairs:
                continue
            seen_pairs.add((a, b))
            fwd = network.relation(r.source_cell_id, r.target_cell_id)
            rev = network.relation(r.target_cell_id, r.source_cell_id)
            rel_attempts += (fwd.ho_attempts if fwd else 0) + (rev.ho_attempts if rev else 0)
            rel_failures += (fwd.ho_failures if fwd else 0) + (rev.ho_failures if rev else 0)
        if rel_attempts > 0:
            total_attempts = rel_attempts
            total_successes = rel_attempts - rel_failures

    ho_success_rate = (total_successes / total_attempts) if total_attempts else None

    n_conflicts = 0
    per_tech: dict[str, dict[str, Any]] = {}
    for tech, sub_cells in (("lte", lte_cells), ("nr", nr_cells)):
        if not sub_cells:
            per_tech[tech] = {"cells": 0, "conflicts": 0}
            continue
        lte_net, nr_net = network.split_by_technology()
        sub = lte_net if tech == "lte" else nr_net
        bundle = all_conflicts(sub, Technology.LTE if tech == "lte" else Technology.NR)
        seen = set()
        for edge_list in (
            bundle.collisions, bundle.confusions,
            bundle.mod3, bundle.mod4, bundle.mod30, bundle.mod6,
        ):
            for e in edge_list:
                seen.add((e.cell_a_id, e.cell_b_id))
        n_collisions = len(bundle.collisions)
        n_confusions = len(bundle.confusions)
        per_tech[tech] = {
            "cells": len(sub_cells),
            "conflicts": len(seen),
            "collisions": n_collisions,
            "confusions": n_confusions,
            "modn": max(0, len(seen) - n_collisions - n_confusions),
        }
        n_conflicts += len(seen)

    return {
        "active_cells": len(cells),
        "active_cells_delta_pct": None,
        "ho_success_rate": ho_success_rate,
        "ho_success_rate_delta_pct": None,
        "active_conflicts": n_conflicts,
        "active_conflicts_delta_abs": None,
        "pending_decisions": 0,
        "by_technology": per_tech,
    }


