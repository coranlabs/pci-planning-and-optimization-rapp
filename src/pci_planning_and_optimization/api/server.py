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

import asyncio
import logging
import os
import re
import time
from contextlib import asynccontextmanager
from pathlib import Path
from typing import Any

from fastapi import FastAPI, File, Form, HTTPException, UploadFile
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import JSONResponse, RedirectResponse, Response
from fastapi.staticfiles import StaticFiles

from pci_planning_and_optimization import __version__
from pci_planning_and_optimization.api import influx_schema as S
from pci_planning_and_optimization.api import plan as plan_mod
from pci_planning_and_optimization.api import services as services_module
from pci_planning_and_optimization.api.auth import init_auth
from pci_planning_and_optimization.api.dashboard_compat import DashboardData
from pci_planning_and_optimization.api.influx import InfluxReader, InfluxWriter
from pci_planning_and_optimization.api.runs import trigger_optimization
from pci_planning_and_optimization.api.services import (
    compute_kpis,
    compute_recent_decisions,
    list_conflicts,
    list_run_files,
    load_run,
    probe_osc,
    synthesize_coords,
)
from pci_planning_and_optimization.api.state import NetworkCache
from pci_planning_and_optimization.app_config import load_config, unfilled


def _package_root() -> Path:
    return Path(__file__).resolve().parent.parent


_log = logging.getLogger("pci_planning_and_optimization.api.server")


async def _start_pm_ingest(app: FastAPI) -> None:
    cfg = getattr(app.state, "config", None)
    cache = getattr(app.state, "network_cache", None)
    if cfg is None or cache is None:
        return
    if cfg.osc.pm_directory:
        _log.info("PM ingest: osc.pm_directory set — reading files from disk, "
                  "Kafka consumer not started")
        return
    if not cfg.osc.kafka.brokers:
        _log.warning("PM ingest: osc.kafka.brokers is empty and no pm_directory "
                     "is set — the rApp has no data source")
        return

    from pci_planning_and_optimization.osc.ingest import PmStore, build_sftp_client
    from pci_planning_and_optimization.osc.ves_consumer import KafkaConsumer

    store = PmStore()
    cache.pm_store = store

    queue: asyncio.Queue = asyncio.Queue()

    k = cfg.osc.kafka
    consumer = KafkaConsumer(
        brokers=k.brokers,
        topic=k.topic,
        consumer_group=k.group_id,
        username=k.username,
        password=k.password,
        security_protocol=k.security_protocol,
        sftp_client=build_sftp_client(cfg),
    )

    async def _drain() -> None:
        while True:
            store.add(await queue.get())

    app.state.pm_consumer = consumer
    app.state.pm_tasks = [
        asyncio.create_task(consumer.start_consuming(queue), name="pm-consume"),
        asyncio.create_task(_drain(), name="pm-drain"),
    ]
    _log.info("PM ingest: consuming %s from %s as group %s",
              k.topic, k.brokers, k.group_id)


async def _stop_pm_ingest(app: FastAPI) -> None:
    consumer = getattr(app.state, "pm_consumer", None)
    if consumer is not None:
        try:
            await consumer.stop()
        except Exception as e:
            _log.warning("PM ingest: consumer stop failed: %s", e)
    for task in getattr(app.state, "pm_tasks", []) or []:
        task.cancel()


@asynccontextmanager
async def _lifespan(app: FastAPI):
    await _start_pm_ingest(app)
    try:
        yield
    finally:
        await _stop_pm_ingest(app)


def create_app(
    ui_dir: Path | None = None,
    runs_dir: Path | None = None,
    config_path: Path | None = None,
) -> FastAPI:
    cwd = Path.cwd()
    ui_dir = ui_dir or _package_root() / "webui"
    runs_dir = runs_dir or cwd / "runs"
    config_path = config_path or cwd / "config" / "config.yaml"
    runs_dir.mkdir(parents=True, exist_ok=True)

    app = FastAPI(
        title="PCI Planning and Optimization rApp",
        version=__version__,
        description="Conservative graph-coloring PCI planner — HTTP surface for the operator UI.",
        lifespan=_lifespan,
    )
    app.add_middleware(
        CORSMiddleware,
        allow_origins=["*"],
        allow_methods=["*"],
        allow_headers=["*"],
        allow_credentials=False,
    )

    app.state.ui_dir = ui_dir
    app.state.runs_dir = runs_dir
    app.state.config_path = config_path
    app.state.started_at = time.time()

    try:
        app.state.config = load_config(str(config_path))
        app.state.config_error = None
        for gap in unfilled(app.state.config):
            _log.warning("%s needs to be configured: %s", config_path, gap)
    except Exception as e:
        app.state.config = None
        app.state.config_error = f"{type(e).__name__}: {e}"

    if app.state.config is not None:
        app.state.network_cache = NetworkCache(
            config=app.state.config, ttl_seconds=30.0,
        )
        app.state.influx_writer = InfluxWriter(cfg=app.state.config.influxdb)
        app.state.influx_reader = InfluxReader(cfg=app.state.config.influxdb)
        app.state.network_cache.influx_writer = app.state.influx_writer
    else:
        app.state.network_cache = None
        app.state.influx_writer = None
        app.state.influx_reader = None

    app.state.plan_store = plan_mod.PlanStore()

    app.state.dashboard = DashboardData(
        config=app.state.config,
        network_cache=app.state.network_cache,
        services_module=services_module,
    )


    init_auth(app, ui_dir)

    @app.get("/", include_in_schema=False)
    def root() -> RedirectResponse:
        return RedirectResponse(url="/ui/index.html")

    @app.get("/api/_meta")
    def meta() -> dict:
        return {
            "name": "pci_planning_and_optimization",
            "version": __version__,
            "started_at": app.state.started_at,
            "uptime_seconds": time.time() - app.state.started_at,
            "ui_dir": str(ui_dir),
            "runs_dir": str(runs_dir),
            "config_path": str(config_path),
            "config_error": app.state.config_error,
            "pid": os.getpid(),
        }


    @app.get("/api/health")
    async def health() -> dict:
        if app.state.config is None:
            return {
                "status": "config_error",
                "version": __version__,
                "config_error": app.state.config_error,
                "components": {
                    "api": {"status": "ok"},
                    "ingest": {"status": "unknown", "note": "config not loaded"},
                    "topology_cache": {"status": "unknown", "note": "config not loaded"},
                    "influxdb": {"status": "unknown", "note": "config not loaded"},
                },
            }

        ingest_probe = await asyncio.to_thread(
            probe_osc, app.state.config.osc, 3.0,
        )
        cache: NetworkCache | None = app.state.network_cache
        snap = await asyncio.to_thread(cache.get) if cache else None
        topo_status = (
            "ok" if (snap and snap.network is not None and snap.last_error is None)
            else ("stale" if snap and snap.network is not None else "down")
        )
        topo_note = (
            f"{len(snap.network.cells)} cells, {len(snap.network.relations)} relations"
            if snap and snap.network is not None
            else (snap.last_error if snap and snap.last_error else "no fetch yet")
        )

        influx_component: dict
        if app.state.influx_reader is None:
            influx_component = {"status": "down", "note": "reader not initialised"}
        else:
            ok, note = await asyncio.to_thread(app.state.influx_reader.ping)
            stats = app.state.influx_writer.stats() if app.state.influx_writer else {}
            full_note = note
            if stats:
                full_note += f"; writer writes_ok={stats.get('writes_ok', 0)} errors={stats.get('write_errors', 0)}"
            influx_component = {"status": "ok" if ok else "down", "note": full_note}

        overall = "ok"
        if ingest_probe["status"] != "ok" or topo_status != "ok":
            overall = "degraded"

        return {
            "status": overall,
            "version": __version__,
            "components": {
                "api": {"status": "ok"},
                "ingest": ingest_probe,
                "topology_cache": {"status": topo_status, "note": topo_note},
                "influxdb": influx_component,
            },
        }


    @app.get("/api/overview/kpis")
    async def overview_kpis() -> dict:
        cache: NetworkCache | None = app.state.network_cache
        if cache is None:
            return _empty_kpis_response("config not loaded")

        snap = await asyncio.to_thread(cache.get)

        def _build() -> dict:
            k = compute_kpis(snap.network)
            recent = compute_recent_decisions(runs_dir, limit=10_000)
            k["pending_decisions"] = recent["pending_total"]
            return k

        kpis = await asyncio.to_thread(_build)

        if app.state.influx_writer is not None:
            def _record() -> None:
                try:
                    app.state.influx_writer.record_kpis(kpis)
                    by_tech = kpis.get("by_technology") or {}
                    if isinstance(by_tech, dict):
                        app.state.influx_writer.record_conflict_summary(by_tech)
                except Exception:
                    pass
            import threading
            threading.Thread(target=_record, name="influx-record-kpis", daemon=True).start()

        return {
            "data": kpis,
            "stale": cache.is_stale(snap),
            "fetched_at": snap.wallclock_at,
            "error": snap.last_error,
            "data_unavailable": snap.network is None,
        }

    @app.get("/api/overview/trend")
    def overview_trend(
        metric: str = "active_conflicts",
        hours: float = 24.0,
        max_samples: int = 200,
    ) -> dict:
        if metric not in S.TREND_METRICS:
            return {
                "data": {"points": [], "metric": metric, "hours": hours},
                "stale": True,
                "fetched_at": time.time(),
                "error": f"unknown metric: {metric}",
            }
        if app.state.influx_reader is None:
            return {
                "data": {"points": [], "metric": metric, "hours": hours},
                "stale": True,
                "fetched_at": time.time(),
                "error": "influxdb is unreachable — trend history unavailable",
            }
        hours = max(0.1, min(hours, 168.0))
        max_samples = max(2, min(max_samples, 1000))
        points, err = app.state.influx_reader.query_trend(
            metric, hours=hours, max_samples=max_samples,
        )
        return {
            "data": {
                "points": points,
                "metric": metric,
                "hours": hours,
                "max_samples": max_samples,
            },
            "stale": err is not None,
            "fetched_at": time.time(),
            "error": err,
        }

    @app.get("/api/overview/recent-decisions")
    def overview_recent_decisions(limit: int = 10) -> dict:
        limit = max(1, min(limit, 200))
        recent = compute_recent_decisions(runs_dir, limit=limit)
        return {
            "data": recent,
            "stale": False,
            "fetched_at": time.time(),
            "error": None,
        }

    @app.get("/api/conflicts")
    async def conflicts(
        severity: str | None = None,
        type: str | None = None,
        technology: str | None = None,
        search: str | None = None,
        page: int = 1,
        page_size: int = 50,
    ) -> dict:
        cache: NetworkCache | None = app.state.network_cache
        if cache is None:
            return {
                "data": list_conflicts(None, app.state.config) if app.state.config else
                        {"items": [], "total": 0, "page": page, "page_size": page_size,
                         "summary": {"critical": 0, "major": 0, "minor": 0,
                                      "by_class": {}, "by_technology": {}}},
                "stale": True, "fetched_at": 0.0,
                "error": app.state.config_error or "config not loaded",
                "data_unavailable": True,
            }
        snap = await asyncio.to_thread(cache.get)
        result = await asyncio.to_thread(
            list_conflicts, snap.network, app.state.config,
            severity=severity, type_filter=type, technology=technology,
            search=search, page=page, page_size=page_size,
        )
        return {
            "data": result,
            "stale": cache.is_stale(snap),
            "fetched_at": snap.wallclock_at,
            "error": snap.last_error,
            "data_unavailable": snap.network is None,
        }


    @app.get("/api/decisions")
    def decisions_list(limit: int = 50, status: str | None = None) -> dict:
        limit = max(1, min(limit, 500))
        items = []
        for path in list_run_files(runs_dir):
            run = load_run(path)
            if run is None:
                continue
            if status and run.get("status") != status:
                continue
            rid = run.get("run_id") or path.stem
            items.append({
                "run_id": rid,
                "technology": run.get("technology"),
                "generated_at": run.get("generated_at"),
                "status": run.get("status", "pending"),
                "applied_at": run.get("applied_at"),
                "n_changes": len(run.get("changes", [])),
                "n_cells": run.get("n_cells", 0),
                "passes_executed": run.get("passes_executed", 0),
                "converged": run.get("converged", False),
                "final_soft_cost": run.get("final_soft_cost", 0.0),
                "error": run.get("error"),
            })
        items.sort(key=lambda it: it.get("generated_at") or "", reverse=True)
        items = items[:limit]
        return {
            "data": {"items": items, "total": len(items)},
            "stale": False, "fetched_at": time.time(), "error": None,
        }

    @app.get("/api/decisions/{run_id}")
    def decisions_detail(run_id: str) -> dict:
        path = runs_dir / f"{run_id}.json"
        if not path.is_file():
            raise HTTPException(status_code=404, detail=f"run not found: {run_id}")
        run = load_run(path)
        if run is None:
            raise HTTPException(status_code=500, detail=f"run unreadable: {run_id}")
        return {
            "data": run,
            "stale": False, "fetched_at": time.time(), "error": None,
        }

    @app.get("/api/decisions/{run_id}/changes/{cell_id}/trace")
    def decisions_trace(run_id: str, cell_id: str) -> dict:
        path = runs_dir / f"{run_id}.json"
        if not path.is_file():
            raise HTTPException(status_code=404, detail=f"run not found: {run_id}")
        run = load_run(path)
        if run is None:
            raise HTTPException(status_code=500, detail=f"run unreadable: {run_id}")
        change = next(
            (c for c in run.get("changes", []) if c.get("cell_id") == cell_id),
            None,
        )
        if change is None:
            raise HTTPException(
                status_code=404,
                detail=f"change for cell {cell_id} not in run {run_id}",
            )
        score_columns = ["mod3_penalty", "mod_aux_penalty", "mod30_penalty",
                          "neg_max_distance", "pci_value"]
        old_key = change.get("sort_key_old", []) or []
        new_key = change.get("sort_key_new", []) or []
        evaluation_matrix = []
        for i, col in enumerate(score_columns):
            evaluation_matrix.append({
                "metric": col,
                "before": old_key[i] if i < len(old_key) else None,
                "after":  new_key[i] if i < len(new_key) else None,
            })
        return {
            "data": {
                "run_id": run.get("run_id"),
                "technology": change.get("technology"),
                "cell_id": change.get("cell_id"),
                "mo_class": change.get("mo_class"),
                "pci_old": change.get("pci_old"),
                "pci_new": change.get("pci_new"),
                "pci_components_new": change.get("pci_components_new"),
                "reason_code": change.get("reason_code"),
                "reason_text": change.get("reason_text"),
                "pass_number": change.get("pass_number"),
                "locked_neighborhood": change.get("locked_neighborhood", []),
                "predicted_ho_failures_avoided_per_week":
                    change.get("predicted_ho_failures_avoided_per_week"),
                "evaluation_matrix": evaluation_matrix,
                "generated_at": run.get("generated_at"),
                "status": change.get("status", "pending"),
                "config_snapshot": run.get("config_snapshot", {}),
            },
            "stale": False, "fetched_at": time.time(), "error": None,
        }

    @app.get("/api/kpi/impact")
    def kpi_impact(run_id: str | None = None) -> dict:
        runs: list[dict] = []
        if run_id:
            path = runs_dir / f"{run_id}.json"
            if not path.is_file():
                raise HTTPException(status_code=404, detail=f"run not found: {run_id}")
            r = load_run(path)
            if r is not None:
                runs.append(r)
        else:
            for path in list_run_files(runs_dir)[:50]:
                r = load_run(path)
                if r is not None:
                    runs.append(r)

        rows = []
        total_predicted = 0.0
        for r in runs:
            rid = r.get("run_id")
            for c in r.get("changes", []):
                pred = c.get("predicted_ho_failures_avoided_per_week", 0.0) or 0.0
                total_predicted += pred
                rows.append({
                    "run_id": rid,
                    "technology": r.get("technology"),
                    "cell_id": c.get("cell_id"),
                    "decision_id": (rid or "") + "::" + (c.get("cell_id") or ""),
                    "pci_old": c.get("pci_old"),
                    "pci_new": c.get("pci_new"),
                    "reason_code": c.get("reason_code"),
                    "predicted_ho_failures_avoided_per_week": pred,
                    "status": c.get("status", "pending"),
                    "applied_at": r.get("applied_at"),
                    "generated_at": r.get("generated_at"),
                })

        rows.sort(key=lambda x: -(x["predicted_ho_failures_avoided_per_week"] or 0.0))

        predicted_by_tech = {"lte": 0.0, "nr": 0.0}
        for row in rows:
            t = (row.get("technology") or "").lower()
            if t in predicted_by_tech:
                predicted_by_tech[t] += float(row.get("predicted_ho_failures_avoided_per_week") or 0.0)

        observed_failures = {"lte": 0, "nr": 0}
        observed_attempts = {"lte": 0, "nr": 0}
        cache_local: NetworkCache | None = app.state.network_cache
        if cache_local is not None:
            snap = cache_local.get()
            if snap.network is not None:
                cells = snap.network.cells
                seen: set = set()
                for r in snap.network.relations:
                    src_cell = cells.get(r.source_cell_id)
                    if src_cell is None:
                        continue
                    tech_key = src_cell.technology.value
                    if tech_key not in observed_failures:
                        continue
                    a, b = sorted([r.source_cell_id, r.target_cell_id])
                    key = (tech_key, a, b)
                    if key in seen:
                        continue
                    seen.add(key)
                    fwd = snap.network.relation(r.source_cell_id, r.target_cell_id)
                    rev = snap.network.relation(r.target_cell_id, r.source_cell_id)
                    pair_failures = (fwd.ho_failures if fwd else 0) + (rev.ho_failures if rev else 0)
                    pair_attempts = (fwd.ho_attempts if fwd else 0) + (rev.ho_attempts if rev else 0)
                    observed_failures[tech_key] += pair_failures
                    observed_attempts[tech_key] += pair_attempts

        def _pct(predicted: float, observed: int) -> float | None:
            if not observed:
                return None
            return min(1.0, predicted / observed)

        per_tech_summary = {
            t: {
                "predicted_avoided": round(predicted_by_tech[t], 1),
                "observed_failures": int(observed_failures[t]),
                "observed_attempts": int(observed_attempts[t]),
                "pct_failures_eliminated": _pct(predicted_by_tech[t], observed_failures[t]),
            }
            for t in ("lte", "nr")
        }
        total_observed_failures = sum(observed_failures.values())
        total_pct_eliminated = _pct(total_predicted, total_observed_failures)

        return {
            "data": {
                "items": rows,
                "total": len(rows),
                "total_predicted_ho_failures_avoided_per_week": round(total_predicted, 1),
                "by_technology": per_tech_summary,
                "total_observed_failures_in_pm_window": total_observed_failures,
                "total_pct_failures_eliminated": total_pct_eliminated,
            },
            "stale": False, "fetched_at": time.time(), "error": None,
        }

    @app.post("/api/optimize/run")
    async def optimize_run(technology: str | None = None) -> dict:
        cache: NetworkCache | None = app.state.network_cache
        if cache is None or app.state.config is None:
            raise HTTPException(status_code=503, detail="config not loaded")
        snap = await asyncio.to_thread(cache.get)
        if snap.network is None:
            raise HTTPException(
                status_code=503,
                detail=f"No network data: {snap.last_error or 'unknown error'}",
            )
        techs = ["lte", "nr"] if not technology else [technology.lower()]
        written = await asyncio.to_thread(
            trigger_optimization, runs_dir, snap.network, app.state.config, techs,
        )
        if app.state.influx_writer is not None:
            for run_dict in written:
                app.state.influx_writer.record_optimization_run(run_dict)
        return {
            "ok": True,
            "runs": [{"run_id": w.get("run_id"),
                       "technology": w.get("technology"),
                       "n_changes": len(w.get("changes", [])),
                       "status": w.get("status")} for w in written],
        }


    @app.get("/api/debug/network")
    async def debug_network(limit: int = 20) -> dict:
        cache: NetworkCache | None = app.state.network_cache
        if cache is None:
            return {"data": {"cells": [], "relations": []}, "error": "config not loaded"}
        snap = await asyncio.to_thread(cache.get)
        if snap.network is None:
            return {"data": {"cells": [], "relations": []},
                    "error": snap.last_error or "no network"}
        cells = list(snap.network.cells.values())[:max(1, min(limit, 200))]
        rels = list(snap.network.relations)[:max(1, min(limit, 200))]
        return {
            "data": {
                "cells": [{
                    "id": c.id, "technology": c.technology.value, "mo_class": c.mo_class,
                    "pci": c.pci, "pci_components": c.pci_components, "duplex": c.duplex,
                    "earfcn_dl": c.earfcn_dl, "arfcn_dl": c.arfcn_dl,
                    "cell_type": c.cell_type, "tac": c.tac,
                    "ho_attempts_total": c.ho_attempts_total,
                    "ho_successes_total": c.ho_successes_total,
                } for c in cells],
                "relations": [{
                    "source_cell_id": r.source_cell_id, "target_cell_id": r.target_cell_id,
                    "ho_attempts": r.ho_attempts, "ho_successes": r.ho_successes,
                    "ho_failures": r.ho_failures, "is_x2_xn": r.is_x2_xn,
                    "relation_source": r.relation_source.value,
                } for r in rels],
                "totals": {
                    "cells": len(snap.network.cells),
                    "relations": len(snap.network.relations),
                    "fetched_at": snap.wallclock_at,
                },
            },
            "fetched_at": snap.wallclock_at,
            "error": snap.last_error,
        }

    @app.get("/api/pipeline/stages")
    async def pipeline_stages() -> dict:
        cache: NetworkCache | None = app.state.network_cache
        snap = await asyncio.to_thread(cache.get) if cache else None
        net = snap.network if snap else None
        runs_present = bool(list_run_files(runs_dir))
        config_loaded = app.state.config is not None

        def stage(name: str, label: str, status: str, note: str, count: int | None = None) -> dict:
            return {"name": name, "label": label, "status": status,
                    "note": note, "count": count}

        stages = [
            stage("kafka_in", "Kafka In",
                  "ok" if net is not None else "down",
                  "PM counters via bounded Kafka consumer"
                  if net is not None else
                  (snap.last_error if snap and snap.last_error else "no fetch yet"),
                  count=(len(net.relations) if net else 0)),
            stage("decode", "Decode",
                  "ok" if net is not None else "idle",
                  "PM XML parsed; topology + PM merged",
                  count=(len(net.cells) if net else 0)),
            stage("enrich", "Enrich",
                  "ok" if net is not None else "idle",
                  "Cells joined to relations and per-cell PM totals",
                  count=(len(net.cells) if net else 0)),
            stage("detect", "Detect",
                  "ok" if net is not None else "idle",
                  "Conflict graph G² built lazily by /api/conflicts",
                  count=None),
            stage("decide", "Decide",
                  "ok" if runs_present else ("idle" if net else "down"),
                  "Conservative graph coloring runs persisted to runs/",
                  count=len(list_run_files(runs_dir))),
        ]
        return {
            "data": {"stages": stages, "config_loaded": config_loaded},
            "stale": cache.is_stale(snap) if cache and snap else True,
            "fetched_at": snap.wallclock_at if snap else 0.0,
            "error": (snap.last_error if snap else app.state.config_error),
        }

    @app.get("/api/config")
    def config_get() -> dict:
        if app.state.config is None:
            return {
                "data": None,
                "stale": False,
                "fetched_at": time.time(),
                "error": app.state.config_error,
            }
        return {
            "data": app.state.config.model_dump(),
            "stale": False,
            "fetched_at": time.time(),
            "error": None,
        }

    @app.put("/api/config")
    def config_put(payload: dict) -> dict:
        try:
            from pci_planning_and_optimization.app_config import AppConfig
            new_cfg = AppConfig.model_validate(payload)
        except Exception as e:
            raise HTTPException(status_code=400, detail=f"validation failed: {e}") from e

        import yaml
        tmp = config_path.with_suffix(".tmp.yaml")
        try:
            with tmp.open("w", encoding="utf-8") as f:
                yaml.safe_dump(new_cfg.model_dump(), f, sort_keys=False)
            os.replace(tmp, config_path)
        except OSError as e:
            raise HTTPException(status_code=500, detail=f"write failed: {e}") from e
        finally:
            try:
                if tmp.exists():
                    tmp.unlink()
            except OSError:
                pass

        if app.state.influx_writer is not None:
            try: app.state.influx_writer.close()
            except Exception: pass
        if app.state.influx_reader is not None:
            try: app.state.influx_reader.close()
            except Exception: pass

        app.state.config = new_cfg
        app.state.config_error = None
        app.state.influx_writer = InfluxWriter(cfg=new_cfg.influxdb)
        app.state.influx_reader = InfluxReader(cfg=new_cfg.influxdb)
        app.state.network_cache = NetworkCache(config=new_cfg, ttl_seconds=30.0)
        app.state.network_cache.influx_writer = app.state.influx_writer
        return {
            "ok": True,
            "data": new_cfg.model_dump(),
            "fetched_at": time.time(),
        }

    @app.get("/api/topology/cells")
    async def topology_cells(limit: int = 5000) -> dict:
        cache: NetworkCache | None = app.state.network_cache
        if cache is None:
            return {"data": {"cells": [], "total": 0,
                              "has_coordinates": False, "synthesized": True,
                              "center": {"lat": 53.3500, "lon": -6.4200}},
                    "stale": True, "fetched_at": 0.0,
                    "error": app.state.config_error or "config not loaded",
                    "data_unavailable": True}
        snap = await asyncio.to_thread(cache.get)
        cells_out: list[dict] = []
        any_real_coords = False
        any_synthesized = False

        if snap.network is not None:
            sev_by_cell: dict[str, str] = {}
            try:
                conflicts = list_conflicts(snap.network, app.state.config, page_size=10_000)
                for row in conflicts.get("items", []):
                    rank = {"critical": 0, "major": 1, "minor": 2}
                    cur = sev_by_cell.get(row["cell_a_id"])
                    if cur is None or rank[row["severity"]] < rank[cur]:
                        sev_by_cell[row["cell_a_id"]] = row["severity"]
                    cur = sev_by_cell.get(row["cell_b_id"])
                    if cur is None or rank[row["severity"]] < rank[cur]:
                        sev_by_cell[row["cell_b_id"]] = row["severity"]
            except Exception as e:
                _log.warning("conflict severity index build failed: %s", e)

            for c in list(snap.network.cells.values())[:max(1, min(limit, 50_000))]:
                if c.lat is not None and c.lon is not None:
                    lat, lon = c.lat, c.lon
                    synthesized = False
                    any_real_coords = True
                else:
                    lat, lon = synthesize_coords(c.id)
                    synthesized = True
                    any_synthesized = True
                row = {
                    "id": c.id,
                    "technology": c.technology.value,
                    "mo_class": c.mo_class,
                    "pci": c.pci,
                    "cell_type": c.cell_type,
                    "lat": lat,
                    "lon": lon,
                    "coords_synthesized": synthesized,
                    "frequency": c.primary_frequency(),
                    "ho_attempts_total": c.ho_attempts_total,
                    "ho_successes_total": c.ho_successes_total,
                    "severity": sev_by_cell.get(c.id),
                }
                cells_out.append(row)

        return {
            "data": {
                "cells": cells_out,
                "total": len(snap.network.cells) if snap.network else 0,
                "has_coordinates": True,
                "any_real_coordinates": any_real_coords,
                "any_synthesized": any_synthesized,
                "center": {"lat": 53.3500, "lon": -6.4200},
            },
            "stale": cache.is_stale(snap),
            "fetched_at": snap.wallclock_at,
            "error": snap.last_error,
            "data_unavailable": snap.network is None,
        }


    @app.post("/api/network/refresh")
    async def network_refresh() -> dict:
        cache: NetworkCache | None = app.state.network_cache
        if cache is None:
            raise HTTPException(
                status_code=503,
                detail=f"config not loaded: {app.state.config_error}",
            )
        snap = await asyncio.to_thread(cache.get, force_refresh=True)
        return {
            "ok": snap.network is not None and snap.last_error is None,
            "fetched_at": snap.wallclock_at,
            "cells": len(snap.network.cells) if snap.network else 0,
            "relations": len(snap.network.relations) if snap.network else 0,
            "error": snap.last_error,
        }


    def _dash() -> DashboardData:
        return app.state.dashboard

    @app.get("/api/dashboard/state")
    async def dashboard_state(
        tech: str | None = None, ts: str | None = None,
    ) -> dict:
        return await asyncio.to_thread(_dash().snapshot, tech, ts)


    @app.post("/api/replan/propose")
    async def replan_propose(payload: dict) -> dict:
        cell_id = (payload or {}).get("cell_id")
        if not cell_id:
            raise HTTPException(status_code=400, detail="cell_id required")
        result = await asyncio.to_thread(_dash().replan_propose, cell_id)
        if not result.get("ok") and "only available" in (result.get("error") or ""):
            return JSONResponse(status_code=503, content=result)
        return result

    @app.post("/api/replan/commit")
    async def replan_commit(payload: dict) -> dict:
        body = payload or {}
        cell_id = body.get("cell_id")
        proposed_pci = body.get("proposed_pci")
        if not cell_id or proposed_pci is None:
            raise HTTPException(
                status_code=400, detail="cell_id and proposed_pci required",
            )
        result = await asyncio.to_thread(_dash().replan_commit, cell_id, proposed_pci)
        if not result.get("ok") and "only available" in (result.get("error") or ""):
            return JSONResponse(status_code=503, content=result)
        return result


    @app.get("/api/audit")
    async def audit_get(
        page: int = 1,
        per_page: int = 50,
        severity: str | None = None,
        type: str | None = None,
        search: str | None = None,
    ) -> dict:
        return await asyncio.to_thread(
            _dash().get_audit,
            page=page, per_page=per_page,
            severity=severity, event_type=type, search=search,
        )

    @app.post("/api/audit")
    async def audit_add(payload: dict) -> dict:
        await asyncio.to_thread(_dash().add_audit, payload or {})
        return {"ok": True}

    @app.get("/api/audit/stats")
    async def audit_stats() -> dict:
        return await asyncio.to_thread(_dash().audit_stats)


    @app.get("/api/settings")
    async def settings_get() -> dict:
        return await asyncio.to_thread(_dash().get_settings)

    @app.post("/api/settings")
    async def settings_set(payload: dict) -> dict:
        await asyncio.to_thread(_dash().set_settings, payload or {})
        return {"ok": True}

    @app.get("/api/excel/template")
    async def excel_template(tech: str | None = None) -> Response:
        data = await asyncio.to_thread(_dash().excel_template_bytes, tech)
        from datetime import datetime as _dt
        stamp = _dt.utcnow().strftime("%Y%m%d-%H%M")
        tech_norm = (tech or "").lower()
        if tech_norm in ("lte", "4g"):
            fname = f"cell-plan-lte-{stamp}.xlsx"
        elif tech_norm in ("nr", "5g"):
            fname = f"cell-plan-5g-{stamp}.xlsx"
        else:
            fname = f"site-config-template-{stamp}.xlsx"
        return Response(
            content=data,
            media_type=(
                "application/vnd.openxmlformats-officedocument."
                "spreadsheetml.sheet"
            ),
            headers={"Content-Disposition": f"attachment; filename={fname}"},
        )

    @app.get("/api/excel/full-pool")
    async def excel_full_pool(tech: str | None = None) -> Response:
        data = await asyncio.to_thread(_dash().full_pool_bytes, tech)
        from datetime import datetime as _dt
        stamp = _dt.utcnow().strftime("%Y%m%d-%H%M")
        tech_norm = (tech or "5g").lower()
        fname = (
            f"pci-pool-lte-{stamp}.xlsx"
            if tech_norm in ("lte", "4g")
            else f"pci-pool-5g-{stamp}.xlsx"
        )
        return Response(
            content=data,
            media_type=(
                "application/vnd.openxmlformats-officedocument."
                "spreadsheetml.sheet"
            ),
            headers={"Content-Disposition": f"attachment; filename={fname}"},
        )


    @app.get("/api/plan/template")
    async def plan_template() -> Response:
        data = await asyncio.to_thread(plan_mod.plan_template_bytes)
        return Response(
            content=data,
            media_type=(
                "application/vnd.openxmlformats-officedocument."
                "spreadsheetml.sheet"
            ),
            headers={"Content-Disposition": "attachment; filename=pci-plan-template.xlsx"},
        )

    @app.get("/api/plan")
    async def plan_list() -> list:
        return app.state.plan_store.list()

    @app.get("/api/plan/samples")
    async def plan_samples() -> list:
        cache: NetworkCache | None = app.state.network_cache
        snap = await asyncio.to_thread(cache.get) if cache else None
        return plan_mod.sample_plans(snap.network if snap else None)

    @app.get("/api/plan/{plan_id}")
    async def plan_get(plan_id: int) -> dict:
        p = app.state.plan_store.get(plan_id)
        if p is None:
            raise HTTPException(status_code=404, detail="Unknown plan id")
        return p

    @app.get("/api/plan/{plan_id}/export")
    async def plan_export(plan_id: int) -> Response:
        p = app.state.plan_store.get(plan_id)
        if p is None:
            raise HTTPException(status_code=404, detail="Unknown plan id")
        rows = app.state.plan_store.export_rows(plan_id)
        data = await asyncio.to_thread(
            plan_mod.plan_workbook_bytes, rows, plan_mod.EXPORT_HEADERS,
        )
        stem = re.sub(r"[^A-Za-z0-9._-]+", "-",
                      p["filename"].rsplit(".", 1)[0]).strip("-") or "plan"
        return Response(
            content=data,
            media_type=(
                "application/vnd.openxmlformats-officedocument."
                "spreadsheetml.sheet"
            ),
            headers={
                "Content-Disposition": f"attachment; filename={stem}-optimised.xlsx",
            },
        )

    @app.post("/api/plan/samples/{region}")
    async def plan_sample_import(region: str) -> dict:
        cache: NetworkCache | None = app.state.network_cache
        snap = await asyncio.to_thread(cache.get) if cache else None
        if snap is None or snap.network is None:
            raise HTTPException(status_code=503, detail="No network data ingested yet")
        network = plan_mod.network_to_plan(snap.network, region)
        if not network.cells:
            raise HTTPException(status_code=404, detail=f"No cells in region {region!r}")
        built = await asyncio.to_thread(
            plan_mod.build_plan, network, app.state.config,
        )
        plan_id = app.state.plan_store.add(f"{region} (sample)", built)
        _dash().add_audit({
            "event_type": "plan_import",
            "description": f"Sample plan imported for {region}: {built['cell_count']} cells, "
                           f"{len(built['changes'])} PCI change(s) proposed",
        })
        return {
            "ok": True, "plan_id": plan_id, "rows": built["cell_count"],
            "before": built["before"]["summary"], "after": built["after"]["summary"],
            "changes": len(built["changes"]),
        }

