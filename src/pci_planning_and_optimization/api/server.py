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


