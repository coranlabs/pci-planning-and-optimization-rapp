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

import json
import logging
import os
import tempfile
import uuid
from datetime import UTC, datetime
from pathlib import Path
from typing import Any

from pci_planning_and_optimization.algorithm.coloring import OptimizationRun, run_optimization
from pci_planning_and_optimization.algorithm.conflict_graph import prepare_network
from pci_planning_and_optimization.app_config import AppConfig
from pci_planning_and_optimization.models import Network, Technology

_log = logging.getLogger("pci_planning_and_optimization.api.runs")


def _gen_run_id(technology: str) -> str:
    ts = datetime.now(UTC).strftime("%Y%m%dT%H%M%SZ")
    short = uuid.uuid4().hex[:8]
    return f"{ts}-{technology}-{short}"


def write_run(
    runs_dir: Path,
    run: OptimizationRun,
    *,
    run_id: str | None = None,
    status: str = "pending",
) -> dict[str, Any]:
    runs_dir.mkdir(parents=True, exist_ok=True)
    rid = run_id or _gen_run_id(run.technology)
    payload = run.to_dict()
    payload["run_id"] = rid
    payload["status"] = status
    payload["applied_at"] = None
    for c in payload.get("changes", []):
        c.setdefault("status", "pending" if status == "pending" else status)

    path = runs_dir / f"{rid}.json"
    fd, tmp_path = tempfile.mkstemp(dir=str(runs_dir), prefix=".tmp-", suffix=".json")
    try:
        with os.fdopen(fd, "w", encoding="utf-8") as f:
            json.dump(payload, f, indent=2, sort_keys=False)
            f.write("\n")
        os.replace(tmp_path, path)
    except Exception:
        try:
            os.unlink(tmp_path)
        except OSError:
            pass
        raise

    _log.info("wrote run %s (%d changes, tech=%s)",
              rid, len(payload.get("changes", [])), run.technology)
    return payload


def trigger_optimization(
    runs_dir: Path,
    network: Network,
    config: AppConfig,
    technologies: list[str],
) -> list[dict[str, Any]]:
    written: list[dict[str, Any]] = []
    for tech_str in technologies:
        tech = Technology.LTE if tech_str.lower() == "lte" else Technology.NR
        lte_net, nr_net = network.split_by_technology()
        sub = lte_net if tech == Technology.LTE else nr_net
        if not sub.cells:
            continue
        prepared = prepare_network(sub, config)
        try:
            run = run_optimization(prepared, tech, config)
            written.append(write_run(runs_dir, run, status="pending"))
        except Exception as e:
            _log.exception("optimization failed for %s", tech_str)
            failed = {
                "run_id": _gen_run_id(tech_str),
                "technology": tech_str,
                "generated_at": datetime.now(UTC).isoformat(timespec="seconds"),
                "status": "failed",
                "applied_at": None,
                "error": f"{type(e).__name__}: {e}",
                "n_cells": len(sub.cells),
                "n_pairs_evaluated": 0,
                "passes_executed": 0,
                "converged": False,
                "final_soft_cost": 0.0,
                "changes": [],
                "pass_history": [],
                "config_snapshot": {},
            }
            path = runs_dir / f"{failed['run_id']}.json"
            with path.open("w", encoding="utf-8") as f:
                json.dump(failed, f, indent=2)
            written.append(failed)
    return written
