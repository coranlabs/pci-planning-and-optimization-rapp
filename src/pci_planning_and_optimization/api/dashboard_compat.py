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
import io
import json
import logging
import threading
import time
from datetime import UTC, datetime
from pathlib import Path
from typing import Any


def _utcnow_iso() -> str:
    return datetime.now(UTC).isoformat()


_COMMIT_CONFIRM_WINDOW_S = 15 * 60

_APPLIED_MARKER = "_pci_overrides_applied"

_UNASSIGNED_REGION = "Unassigned"

_HISTORY_STEP_S = 60
_HISTORY_MAX = 24 * 60


_FULL_NAMESPACE = {"LTE": (0, 504), "NR": (0, 1008)}


def _pci_pool_range(config: Any, cell: Any) -> tuple[int, int]:
    tech = cell.technology.name
    default = _FULL_NAMESPACE.get(tech, (0, 504))
    try:
        pools = getattr(config.pools, tech.lower())
        rng = getattr(pools, cell.cell_type, None)
    except AttributeError:
        return default
    if not rng or len(rng) != 2:
        return default
    return int(rng[0]), int(rng[1])


def _change_record(cell: Any, new_pci: int) -> dict[str, Any]:
    record: dict[str, Any] = {
        "cell_id": cell.dn or cell.id,
        "technology": cell.technology.name.lower(),
        "mo_class": cell.mo_class,
        "pci_new": new_pci,
    }
    if cell.technology.name == "LTE":
        record["pci_components_new"] = {"group": new_pci // 3, "sub": new_pci % 3}
    return record


def compute_pulse(
    cells: list[dict[str, Any]],
    conflicts: list[dict[str, Any]],
) -> dict[str, Any]:
    total_cells = len(cells)
    active_cells = sum(1 for c in cells if c.get("status") == "active")

    affected_ues = sum(int(c.get("affectedUe") or 0) for c in conflicts)

    region_by_cell: dict[str, str] = {
        c["id"]: c.get("region", "—") for c in cells if c.get("id")
    }
    region_conflicts: dict[str, int] = {}
    region_ues: dict[str, int] = {}
    for cf in conflicts:
        regions_touched = {
            region_by_cell.get(cid)
            for cid in (cf.get("cells") or [])
            if region_by_cell.get(cid)
        }
        ue = int(cf.get("affectedUe") or 0)
        for r in regions_touched:
            region_conflicts[r] = region_conflicts.get(r, 0) + 1
            region_ues[r] = region_ues.get(r, 0) + ue
    worst_region: dict[str, Any] | None = None
    if region_conflicts:
        name = max(region_conflicts, key=lambda r: region_conflicts[r])
        worst_region = {
            "name": name,
            "conflicts": region_conflicts[name],
            "ues": region_ues.get(name, 0),
        }

    mod3_cell_ids = {
        cid
        for cf in conflicts
        if cf.get("type") == "mod3"
        for cid in (cf.get("cells") or [])
    }

    return {
        "activeCells": active_cells,
        "totalCells": total_cells,
        "affectedUes": affected_ues,
        "conflictCount": len(conflicts),
        "worstRegion": worst_region,
        "mod3Cells": len(mod3_cell_ids),
    }


