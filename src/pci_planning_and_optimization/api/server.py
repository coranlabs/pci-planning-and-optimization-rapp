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

