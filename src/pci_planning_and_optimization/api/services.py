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


def list_run_files(runs_dir: Path) -> list[Path]:
    if not runs_dir.is_dir():
        return []
    files = [p for p in runs_dir.glob("*.json") if p.is_file()]
    files.sort(key=lambda p: p.stat().st_mtime, reverse=True)
    return files


def load_run(path: Path) -> dict[str, Any] | None:
    try:
        with path.open("r", encoding="utf-8") as f:
            return json.load(f)
    except (OSError, json.JSONDecodeError) as e:
        _log.warning("failed to read run file %s: %s", path, e)
        return None


def compute_recent_decisions(
    runs_dir: Path,
    limit: int = 10,
) -> dict[str, Any]:
    rows: list[dict[str, Any]] = []
    pending_total = 0
    for run_path in list_run_files(runs_dir):
        run = load_run(run_path)
        if run is None:
            continue
        run_id = run.get("run_id") or run_path.stem
        for change in run.get("changes", []):
            row = {
                "run_id": run_id,
                "cell_id": change.get("cell_id"),
                "pci_old": change.get("pci_old"),
                "pci_new": change.get("pci_new"),
                "conflict_type": _humanize_reason(change.get("reason_code")),
                "technology": change.get("technology"),
                "status": change.get("status", "pending"),
                "generated_at": run.get("generated_at"),
            }
            rows.append(row)
            if row["status"] == "pending":
                pending_total += 1
            if len(rows) >= limit:
                break
        if len(rows) >= limit:
            break

    return {
        "items": rows,
        "pending_total": pending_total,
        "total_runs": len(list_run_files(runs_dir)),
    }


_CLASS_SEVERITY = {
    CLASS_COLLISION: ("critical", "Collision"),
    CLASS_CONFUSION: ("major", "Confusion"),
    "mod3": ("minor", "Mod-3"),
    "mod4": ("minor", "Mod-4"),
    "mod30": ("minor", "Mod-30"),
    "mod6": ("minor", "Mod-6"),
}

_CLASS_PRECEDENCE = [
    CLASS_COLLISION, CLASS_CONFUSION, "mod3", "mod4", "mod6", "mod30",
]


def list_conflicts(
    network: Network | None,
    config: AppConfig,
    *,
    severity: str | None = None,
    type_filter: str | None = None,
    technology: str | None = None,
    search: str | None = None,
    page: int = 1,
    page_size: int = 50,
) -> dict[str, Any]:
    if network is None:
        return {"items": [], "total": 0, "page": page, "page_size": page_size,
                "summary": {"critical": 0, "major": 0, "minor": 0,
                             "by_class": {}, "by_technology": {}}}

    page_size = max(1, min(page_size, 200))
    page = max(1, page)

    enable_mod6 = bool(config.scoring.lte.enable_mod6)
    pair_class: dict[tuple, Any] = {}
    for tech_str, tech_enum in (("lte", Technology.LTE), ("nr", Technology.NR)):
        if technology and technology.lower() != tech_str:
            continue
        sub = network.split_by_technology()[0 if tech_enum == Technology.LTE else 1]
        if not sub.cells:
            continue
        bundle = all_conflicts(sub, tech_enum, enable_mod6_lte=enable_mod6)
        per_class = {
            CLASS_COLLISION: bundle.collisions,
            CLASS_CONFUSION: bundle.confusions,
            "mod3": bundle.mod3,
            "mod4": bundle.mod4,
            "mod6": bundle.mod6,
            "mod30": bundle.mod30,
        }
        for klass in _CLASS_PRECEDENCE:
            for edge in per_class.get(klass, []):
                key = (edge.cell_a_id, edge.cell_b_id)
                if key not in pair_class:
                    edge_dict = edge.to_dict()
                    edge_dict["conflict_class"] = klass
                    sev, label = _CLASS_SEVERITY.get(klass, ("minor", klass))
                    edge_dict["severity"] = sev
                    edge_dict["type_label"] = label
                    pair_class[key] = edge_dict

    rows = list(pair_class.values())

    summary = {
        "critical": sum(1 for r in rows if r["severity"] == "critical"),
        "major":    sum(1 for r in rows if r["severity"] == "major"),
        "minor":    sum(1 for r in rows if r["severity"] == "minor"),
        "by_class": {},
        "by_technology": {"lte": 0, "nr": 0},
    }
    for r in rows:
        summary["by_class"][r["conflict_class"]] = summary["by_class"].get(r["conflict_class"], 0) + 1
        summary["by_technology"][r["technology"]] = summary["by_technology"].get(r["technology"], 0) + 1

    if severity:
        rows = [r for r in rows if r["severity"] == severity.lower()]
    if type_filter:
        rows = [r for r in rows if r["type_label"].lower() == type_filter.lower()]
    if search:
        s = search.lower()
        rows = [r for r in rows
                if s in r["cell_a_id"].lower() or s in r["cell_b_id"].lower()]

    sev_rank = {"critical": 0, "major": 1, "minor": 2}
    rows.sort(key=lambda r: (sev_rank.get(r["severity"], 9),
                              -int(r.get("ho_failures") or 0),
                              r["cell_a_id"], r["cell_b_id"]))

    total = len(rows)
    start = (page - 1) * page_size
    end = start + page_size
    page_rows = rows[start:end]

    for r in page_rows:
        r["pci_a_display"] = r["pci_a"]
        r["pci_b_display"] = r["pci_b"]

    return {
        "items": page_rows,
        "total": total,
        "page": page,
        "page_size": page_size,
        "summary": summary,
    }


def _humanize_reason(reason_code: str | None) -> str:
    if not reason_code:
        return "Unknown"
    code = reason_code.upper()
    if "COLLISION" in code:
        return "Collision"
    if "CONFUSION" in code:
        return "Confusion"
    if "MOD3" in code:
        return "Mod-3"
    if "MOD4" in code:
        return "Mod-4"
    if "MOD30" in code:
        return "Mod-30"
    if "MOD6" in code:
        return "Mod-6"
    return reason_code


def probe_osc(config_osc, timeout_s: float = 3.0) -> dict[str, Any]:
    pm_dir = getattr(config_osc, "pm_directory", "")
    if pm_dir:
        from pathlib import Path as _Path

        d = _Path(pm_dir)
        if not d.is_dir():
            return {"status": "down", "note": f"PM directory not found: {pm_dir}"}
        n = sum(1 for _ in d.glob("*.xml"))
        if n == 0:
            return {"status": "down", "note": f"no *.xml files in {pm_dir}"}
        return {"status": "ok", "note": f"{n} PM files in {pm_dir}"}

    kafka = getattr(config_osc, "kafka", None)
    if kafka is None or not kafka.brokers:
        return {
            "status": "unconfigured",
            "note": "osc.kafka.brokers is empty and osc.pm_directory is unset",
        }
    return {
        "status": "ok",
        "note": f"subscribed to {kafka.topic} on {kafka.brokers}",
    }
