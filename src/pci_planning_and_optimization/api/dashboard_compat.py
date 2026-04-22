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


_log = logging.getLogger(__name__)

_THP_STEP_S = 60
_THP_MAX_AGE_S = 7 * 86400
_TS_RANGES: dict[str, int] = {
    "15m": 15 * 60, "1h": 3600, "6h": 6 * 3600, "24h": 86400, "7d": 7 * 86400,
}
_TS_DEFAULT = "1h"
_TS_TARGET_POINTS = 120


def _resample(pts: list[list[float]], span: float) -> list[dict[str, Any]]:
    if not pts:
        return []
    now = time.time()
    step = max(_THP_STEP_S, span / _TS_TARGET_POINTS)
    slots = int(span / step)
    start = now - slots * step

    acc = [[0.0, 0.0, 0] for _ in range(slots)]
    for ts, dl, ul in pts:
        i = int((ts - start) / step)
        if 0 <= i < slots:
            acc[i][0] += dl
            acc[i][1] += ul
            acc[i][2] += 1

    filled = [i for i, a in enumerate(acc) if a[2]]
    if not filled:
        return []

    out: list[dict[str, Any]] = []
    last = (0.0, 0.0)
    for i in range(filled[0], filled[-1] + 1):
        dl, ul, n = acc[i]
        if n:
            last = (dl / n, ul / n)
        stamp = datetime.fromtimestamp(start + (i + 1) * step, UTC)
        out.append({
            "t": stamp.strftime("%H:%M"), "iso": stamp.isoformat(),
            "dl": round(last[0]), "ul": round(last[1]),
        })
    return out


class ThroughputHistory:

    def __init__(self, path: str = "") -> None:
        self._path = Path(path) if path else None
        self._lock = threading.Lock()
        self._series: dict[str, list[list[float]]] = {}
        self._load()

    def _load(self) -> None:
        if self._path is None or not self._path.exists():
            return
        try:
            raw = json.loads(self._path.read_text(encoding="utf-8"))
            cutoff = time.time() - _THP_MAX_AGE_S
            self._series = {
                tech: [[float(t), float(dl), float(ul)] for t, dl, ul in pts if t >= cutoff]
                for tech, pts in (raw.get("series") or {}).items()
            }
            _log.debug(
                "throughput history loaded from %s: %s",
                self._path, {k: len(v) for k, v in self._series.items()},
            )
        except (OSError, ValueError, TypeError) as e:
            _log.warning("throughput history %s unreadable (%s) — starting empty", self._path, e)
            self._series = {}

    def _flush(self) -> None:
        if self._path is None:
            return
        tmp = self._path.with_suffix(self._path.suffix + ".tmp")
        try:
            tmp.parent.mkdir(parents=True, exist_ok=True)
            tmp.write_text(json.dumps({"series": self._series}), encoding="utf-8")
            tmp.replace(self._path)
        except OSError as e:
            _log.warning("throughput history %s not written: %s", self._path, e)

    def record(self, tech: str, dl: float, ul: float) -> None:
        now = time.time()
        with self._lock:
            pts = self._series.setdefault(tech, [])
            if pts and now - pts[-1][0] < _THP_STEP_S:
                return
            pts.append([now, round(dl, 1), round(ul, 1)])
            cutoff = now - _THP_MAX_AGE_S
            while pts and pts[0][0] < cutoff:
                pts.pop(0)
            self._flush()

    def record_network(self, network: Any) -> None:
        totals: dict[str, list[float]] = {}
        for cell in network.cells.values():
            t = totals.setdefault(_tech_of(cell), [0.0, 0.0])
            t[0] += (cell.thp_dl_kbps or 0.0) / 1000.0
            t[1] += (cell.thp_ul_kbps or 0.0) / 1000.0
        for tech, (dl, ul) in totals.items():
            self.record(tech, dl, ul)

    def window(self, tech: str, range_key: str | None) -> list[dict[str, Any]]:
        span = _TS_RANGES.get(range_key or "", _TS_RANGES[_TS_DEFAULT])
        floor = time.time() - span
        with self._lock:
            pts = [p for p in self._series.get(tech, []) if p[0] >= floor]
        return _resample(pts, span)


_ALERT_KIND = {"collision": "PCI Collision", "confusion": "PCI Confusion", "mod3": "Mod-3"}
_SEV_RANK = {"critical": 0, "major": 1, "minor": 2, "info": 3}


def _build_alerts(
    cells: list[dict[str, Any]],
    conflicts: list[dict[str, Any]],
    first_seen: dict[str, str],
    prb_warning: float = 80.0,
) -> list[dict[str, Any]]:
    now = _utcnow_iso()
    out: list[dict[str, Any]] = []

    def add(key: str, sev: str, cell: str, kind: str, msg: str) -> None:
        digest = hashlib.md5(key.encode("utf-8"), usedforsecurity=False).hexdigest()[:8]
        aid = f"AL-{digest}"
        iso = first_seen.setdefault(aid, now)
        out.append({
            "id": aid, "sev": sev, "t": iso[11:19], "iso": iso,
            "cell": cell, "kind": kind, "msg": msg,
        })

    for cf in conflicts:
        ids = cf.get("cells") or []
        add("|".join([cf["type"], str(cf.get("pci")), *sorted(map(str, ids))]),
            cf["severity"], ids[0] if ids else "—",
            _ALERT_KIND.get(cf["type"], "PCI"), cf["impact"])

    over = sorted((c for c in cells if c["prb"] >= prb_warning), key=lambda c: -c["prb"])
    congested = over[:10]
    if len(over) > len(congested):
        add(f"prb-summary|{prb_warning:.0f}", "major", "—", "PRB Congestion",
            f"{len(over)} cells above {prb_warning:.0f}% PRB utilisation — the {len(congested)} "
            f"worst are listed; raise the threshold in Settings to narrow")
    for c in congested:
        add(f"prb|{c['id']}", "major" if c["prb"] >= prb_warning + 10 else "minor", c["id"],
            "PRB Congestion",
            f"PRB utilisation at {c['prb']:.0f}% on {c['id']} (threshold {prb_warning:.0f}%)")

    out.sort(key=lambda a: (_SEV_RANK.get(a["sev"], 9), a["t"], a["cell"]))
    return out


def _tech_of(cell: Any) -> str:
    return str(getattr(cell.technology, "value", cell.technology)).lower()


def _cells_by_tech(network: Any) -> dict[str, int]:
    counts = {"lte": 0, "nr": 0}
    for cell in network.cells.values():
        t = _tech_of(cell)
        counts[t] = counts.get(t, 0) + 1
    return counts


def _resolve_tech(network: Any, tech: str | None) -> str:
    if tech in ("lte", "nr"):
        return tech
    counts = _cells_by_tech(network)
    return "nr" if counts["nr"] or not counts["lte"] else "lte"


def build_real_pci_data(
    network: Any,
    conflicts_result: dict[str, Any] | None,
    *,
    synthesize_coords: Any,
    alert_first_seen: dict[str, str] | None = None,
    tech: str | None = None,
    prb_warning: float = 80.0,
) -> dict[str, Any]:
    if network is None:
        return _empty_pci_data(mode="live", note="no PM data ingested yet")

    cells_by_tech = _cells_by_tech(network)
    tech = _resolve_tech(network, tech)

    cells_out: list[dict[str, Any]] = []
    for cell in network.cells.values():
        if _tech_of(cell) != tech:
            continue
        prb = round((cell.prb_util or 0.0) * 100, 0)
        real_pos = cell.lat is not None and cell.lon is not None
        if real_pos:
            lat, lng = cell.lat, cell.lon
        else:
            lat, lng = synthesize_coords(cell.id)
        neighbor_pcis: list[int] = []
        for n in network.neighbors_of(cell.id, same_tech_only=True):
            if n.pci not in neighbor_pcis:
                neighbor_pcis.append(n.pci)
        freq = cell.primary_frequency()
        mod_conflicts: dict[str, list[str]] = {"mod3": [], "mod4": [], "mod30": []}
        for n in network.neighbors_of(cell.id, same_tech_only=True):
            if freq is None or n.primary_frequency() != freq:
                continue
            if n.pci == cell.pci:
                continue
            for mod in (3, 4, 30):
                if n.pci % mod == cell.pci % mod:
                    mod_conflicts[f"mod{mod}"].append(n.id)
        if cell.band is not None:
            band_label = f"n{cell.band}" if tech == "nr" else f"B{cell.band}"
        elif freq is None:
            band_label = "—"
        elif tech == "lte":
            band_label = f"B{freq}"
        else:
            band_label = f"n{freq}"
        cells_out.append({
            "id": cell.id,
            "tech": tech,
            "site": cell.id.rsplit("-", 1)[0] if "-" in cell.id else cell.id,
            "region": cell.region or _UNASSIGNED_REGION,
            "pci": cell.pci,
            "band": band_label,
            "arfcn": freq,
            "sector": 1,
            "status": "active",
            "dl": round((cell.thp_dl_kbps or 0.0) / 1000.0, 1),
            "ul": round((cell.thp_ul_kbps or 0.0) / 1000.0, 1),
            "prb": prb,
            "ue": int(cell.active_ues or 0),
            "bler": round(cell.bler_dl or 0.0, 2),
            "cqi": round(cell.cqi or 0.0, 1),
            "sinr": round(cell.sinr_db or 0.0, 1),
            "lat": lat, "lng": lng, "approxPos": not real_pos,
            "neighbors": neighbor_pcis[:5],
            "neighborCount": len(neighbor_pcis),
            "modConflicts": mod_conflicts,
            "height_m": cell.antenna_height,
            "azimuth": cell.azimuth,
            "mech_tilt": None, "elec_tilt": None,
            "antenna_model": None, "antenna_gain_dbi": None,
            "beamwidth_deg": None, "tx_power_dbm": None,
        })

    ue_by_cell = {c["id"]: int(c["ue"]) for c in cells_out}
    conflicts_out: list[dict[str, Any]] = []
    if conflicts_result:
        for i, row in enumerate(conflicts_result.get("items", [])):
            cls = row.get("conflict_class", "")
            if cls == "collision":
                ctype = "collision"
            elif cls == "confusion":
                ctype = "confusion"
            else:
                ctype = "mod3"
            conflicts_out.append({
                "id": f"CFL-{2040 + i + 1}",
                "type": ctype,
                "pci": row.get("pci_a"),
                "severity": row.get("severity", "minor"),
                "cells": [row.get("cell_a_id"), row.get("cell_b_id")],
                "detected": _utcnow_iso(),
                "impact": (
                    f"{row.get('type_label', 'Conflict')} on "
                    f"{row.get('cell_a_id')} / {row.get('cell_b_id')} "
                    f"(PCI {row.get('pci_a')})"
                ),
                "affectedUe": ue_by_cell.get(str(row.get("cell_a_id")), 0)
                + ue_by_cell.get(str(row.get("cell_b_id")), 0),
            })

    total = len(cells_out)
    kpis = {
        "activeCells": total,
        "totalCells": total,
        "pciConflicts": len(conflicts_out),
        "pciTotal": len(conflicts_out),
        "coverage": 100.0 if total else 0.0,
        "coverageDelta": 0.0,
        "errorRate": round(sum(c["bler"] for c in cells_out) / total, 2) if total else 0.0,
        "errorRateDelta": 0.0,
        "connectedUe": sum(c["ue"] for c in cells_out),
        "connectedUeDelta": 0,
        "pulse": compute_pulse(cells_out, conflicts_out),
    }

    by_region: dict[str, list[dict[str, Any]]] = {}
    for c in cells_out:
        by_region.setdefault(c["region"], []).append(c)
    conflicted_ids = {cid for cf in conflicts_out for cid in cf["cells"]}

    regions_health = []
    for r in sorted(by_region):
        in_region = by_region[r]
        ids = {ic["id"] for ic in in_region}
        ok = sum(1 for ic in in_region if ic["id"] not in conflicted_ids)
        regions_health.append({
            "name": r,
            "cells": len(in_region),
            "ok": ok,
            "pct": round(100 * ok / len(in_region)) if in_region else 0,
            "conflicts": sum(1 for c in conflicts_out if ids & set(c["cells"])),
        })

    return {
        "CELLS": cells_out,
        "CONFLICTS": conflicts_out,
        "ALERTS": _build_alerts(
            cells_out, conflicts_out,
            alert_first_seen if alert_first_seen is not None else {},
            prb_warning=prb_warning,
        ),
        "TS": [],
        "SLICES": [],
        "KPIS": kpis,
        "REGIONS_HEALTH": regions_health,
        "meta": {
            "mode": "live",
            "updated": _utcnow_iso(),
            "poll_error": None,
            "tech": tech,
            "cellsByTech": cells_by_tech,
        },
    }


