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
from collections.abc import Iterable
from typing import Any

from pci_planning_and_optimization.models import (
    Cell,
    NeighborRelation,
    Network,
    RelationSource,
    Technology,
)

_log = logging.getLogger(__name__)

__all__ = ["PM_COUNTER_NAMES", "build_network_from_pm"]


PM_COUNTER_NAMES: dict[str, str] = {
    "pci": "CELL.Pci",
    "tac": "CELL.Tac",
    "arfcn_dl": "CELL.ArfcnDl",
    "arfcn_ul": "CELL.ArfcnUl",
    "bandwidth": "CELL.BandwidthDlMhz",
    "plmn_mcc": "CELL.PlmnMcc",
    "plmn_mnc": "CELL.PlmnMnc",
    "prb_util": "CELL.PrbUtilDlPct",
    "thp_dl_kbps": "CELL.ThroughputDlKbps",
    "thp_ul_kbps": "CELL.ThroughputUlKbps",
    "active_ues": "CELL.ActiveUeCount",
    "cqi": "CELL.AvgCqi",
    "sinr_db": "CELL.AvgSinrDb",
    "bler_dl": "CELL.DlBler",
    "lat": "TOPO.Latitude",
    "lon": "TOPO.Longitude",
    "site_type": "TOPO.SiteType",
    "region": "TOPO.Region",
    "neighbors": "TOPO.Neighbors",
    "band": "CELL.BandNumber",
}

_LDN_CLASS_MAP: tuple[tuple[str, Technology, str], ...] = (
    ("NRCellDU=", Technology.NR, "NRCellDU"),
    ("EUtranCellFDD=", Technology.LTE, "EUtranCellFDD"),
    ("EUtranCellTDD=", Technology.LTE, "EUtranCellTDD"),
)

_ALLOWED_CELL_TYPES = {"macro", "small", "das", "indoor"}


def _num(raw: str | None) -> float | None:
    if raw is None or raw == "":
        return None
    try:
        return float(raw)
    except (TypeError, ValueError):
        return None


def _int(raw: str | None) -> int | None:
    v = _num(raw)
    return None if v is None else int(v)


def _classify(ldn: str) -> tuple[Technology, str, str] | None:
    for token, tech, mo_class in _LDN_CLASS_MAP:
        idx = ldn.find(token)
        if idx == -1:
            continue
        tail = ldn[idx + len(token):]
        cell_id = tail.split(",", 1)[0].strip()
        if cell_id:
            return tech, mo_class, cell_id
    return None


_RELATION_TOKENS: tuple[str, ...] = ("NRCellRelation=", "EUtranCellRelation=")

REL_COUNTER_NAMES: dict[str, str] = {
    "attempts": "REL.HoAttempts",
    "successes": "REL.HoSuccesses",
    "failures": "REL.HoFailures",
    "prep_failures": "REL.HoPrepFailures",
}


def _split_relation_ldn(ldn: str) -> tuple[str, str] | None:
    for token in _RELATION_TOKENS:
        idx = ldn.find(token)
        if idx == -1:
            continue
        target = ldn[idx + len(token):].split(",", 1)[0].strip()
        classified = _classify(ldn[:idx])
        if classified is None or not target:
            return None
        return classified[2], target
    return None


def _collect_relations(
    per_object: dict[str, dict[str, str]],
    out: dict[tuple[str, str], dict[str, float]],
) -> None:
    for ldn, attrs in per_object.items():
        pair = _split_relation_ldn(ldn)
        if pair is None:
            continue
        counters = {
            key: _num(attrs.get(name))
            for key, name in REL_COUNTER_NAMES.items()
        }
        if all(v is None for v in counters.values()):
            continue
        out[pair] = {k: (v or 0.0) for k, v in counters.items()}


def _node_topology(per_object: dict[str, dict[str, str]]) -> dict[str, str]:
    for attrs in per_object.values():
        if PM_COUNTER_NAMES["lat"] in attrs or PM_COUNTER_NAMES["neighbors"] in attrs:
            return attrs
    return {}


def build_network_from_pm(pm_files: Iterable[Any]) -> Network:
    cells_by_id: dict[str, Cell] = {}
    cells_by_node: dict[str, list[str]] = {}
    node_neighbors: dict[str, list[str]] = {}
    measured_relations: dict[tuple[str, str], dict[str, float]] = {}

    for pm in pm_files:
        per_object: dict[str, dict[str, str]] = getattr(pm, "per_object", {}) or {}
        if not per_object:
            continue

        _collect_relations(per_object, measured_relations)

        node_name = getattr(pm, "source_name", "") or ""
        topo = _node_topology(per_object)

        lat = _num(topo.get(PM_COUNTER_NAMES["lat"]))
        lon = _num(topo.get(PM_COUNTER_NAMES["lon"]))
        region = topo.get(PM_COUNTER_NAMES["region"]) or None
        site_type = (topo.get(PM_COUNTER_NAMES["site_type"]) or "macro").strip().lower()
        if site_type not in _ALLOWED_CELL_TYPES:
            _log.debug(
                "node %s: unknown TOPO.SiteType %r — defaulting to 'macro'",
                node_name, site_type,
            )
            site_type = "macro"

        neighbors_raw = topo.get(PM_COUNTER_NAMES["neighbors"]) or ""
        if neighbors_raw:
            node_neighbors[node_name] = [
                n.strip() for n in neighbors_raw.split(",") if n.strip()
            ]

        for ldn, attrs in per_object.items():
            classified = _classify(ldn)
            if classified is None:
                continue
            tech, mo_class, cell_id = classified

            pci = _int(attrs.get(PM_COUNTER_NAMES["pci"]))
            if pci is None:
                continue

            prb = _num(attrs.get(PM_COUNTER_NAMES["prb_util"]))
            mcc = attrs.get(PM_COUNTER_NAMES["plmn_mcc"]) or None
            mnc = attrs.get(PM_COUNTER_NAMES["plmn_mnc"]) or None

            arfcn_dl = _int(attrs.get(PM_COUNTER_NAMES["arfcn_dl"]))
            arfcn_ul = _int(attrs.get(PM_COUNTER_NAMES["arfcn_ul"]))
            bandwidth = _int(attrs.get(PM_COUNTER_NAMES["bandwidth"]))
            tac = _int(attrs.get(PM_COUNTER_NAMES["tac"]))

            common: dict[str, Any] = {
                "id": cell_id,
                "dn": ldn,
                "technology": tech,
                "mo_class": mo_class,
                "pci": pci,
                "bandwidth_mhz": bandwidth,
                "tac": tac,
                "plmn_mcc": str(mcc) if mcc is not None else None,
                "plmn_mnc": str(mnc) if mnc is not None else None,
                "lat": lat,
                "lon": lon,
                "cell_type": site_type,
                "region": region,
                "band": _int(attrs.get(PM_COUNTER_NAMES["band"])),
                "prb_util": (prb / 100.0) if prb is not None else None,
                "thp_dl_kbps": _num(attrs.get(PM_COUNTER_NAMES["thp_dl_kbps"])),
                "thp_ul_kbps": _num(attrs.get(PM_COUNTER_NAMES["thp_ul_kbps"])),
                "active_ues": _int(attrs.get(PM_COUNTER_NAMES["active_ues"])),
                "cqi": _num(attrs.get(PM_COUNTER_NAMES["cqi"])),
                "sinr_db": _num(attrs.get(PM_COUNTER_NAMES["sinr_db"])),
                "bler_dl": _num(attrs.get(PM_COUNTER_NAMES["bler_dl"])),
            }
            if tech == Technology.NR:
                common["arfcn_dl"] = arfcn_dl
                common["arfcn_ul"] = arfcn_ul
            else:
                common["earfcn_dl"] = arfcn_dl
                common["earfcn_ul"] = arfcn_ul
                common["pci_components"] = (pci // 3, pci % 3)
                common["duplex"] = "TDD" if mo_class.endswith("TDD") else "FDD"
                if common["duplex"] == "TDD":
                    common["earfcn_ul"] = None

            try:
                cells_by_id[cell_id] = Cell(**common)
            except Exception as exc:
                _log.warning("skipping cell %s: %s", cell_id, exc)
                continue

            cells_by_node.setdefault(node_name, [])
            if cell_id not in cells_by_node[node_name]:
                cells_by_node[node_name].append(cell_id)

    if measured_relations:
        relations = _measured_relations(cells_by_id, measured_relations)
        source = "measured NRT"
    else:
        relations = _expand_relations(cells_by_id, cells_by_node, node_neighbors)
        source = "inferred from node adjacency"

    _log.info(
        "OSC PM -> Network: %d cells, %d relations (%s, %d nodes)",
        len(cells_by_id), len(relations), source, len(cells_by_node),
    )
    return Network(list(cells_by_id.values()), relations)


def _measured_relations(
    cells_by_id: dict[str, Cell],
    measured: dict[tuple[str, str], dict[str, float]],
) -> list[NeighborRelation]:
    out: list[NeighborRelation] = []
    for (src, tgt), counters in measured.items():
        a = cells_by_id.get(src)
        b = cells_by_id.get(tgt)
        if a is None or b is None:
            continue
        attempts = int(counters.get("attempts", 0))
        failures = int(counters.get("failures", 0))
        successes = int(counters.get("successes", max(0, attempts - failures)))
        out.append(
            NeighborRelation(
                source_cell_id=src,
                target_cell_id=tgt,
                ho_attempts=attempts,
                ho_successes=successes,
                ho_failures=failures,
                ho_prep_failures=int(counters.get("prep_failures", 0)),
                cross_technology=(a.technology != b.technology),
                relation_source=RelationSource.REAL,
            )
        )
    return out


def _expand_relations(
    cells_by_id: dict[str, Cell],
    cells_by_node: dict[str, list[str]],
    node_neighbors: dict[str, list[str]],
) -> list[NeighborRelation]:
    out: list[NeighborRelation] = []
    seen: set[tuple[str, str]] = set()

    def add(a_id: str, b_id: str) -> None:
        if a_id == b_id:
            return
        a = cells_by_id.get(a_id)
        b = cells_by_id.get(b_id)
        if a is None or b is None:
            return
        for src, dst in ((a_id, b_id), (b_id, a_id)):
            if (src, dst) in seen:
                continue
            seen.add((src, dst))
            out.append(
                NeighborRelation(
                    source_cell_id=src,
                    target_cell_id=dst,
                    cross_technology=(a.technology != b.technology),
                    relation_source=RelationSource.SHADOW,
                )
            )

    for cell_ids in cells_by_node.values():
        for i, a_id in enumerate(cell_ids):
            for b_id in cell_ids[i + 1:]:
                add(a_id, b_id)

    for node, peers in node_neighbors.items():
        local = cells_by_node.get(node, [])
        if not local:
            continue
        for peer in peers:
            for a_id in local:
                for b_id in cells_by_node.get(peer, []):
                    add(a_id, b_id)

    return out
