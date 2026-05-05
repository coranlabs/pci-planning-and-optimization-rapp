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
import signal
from collections.abc import Awaitable, Callable
from contextlib import suppress
from typing import Any

import uvicorn
from fastapi import FastAPI

from pci_planning_and_optimization import (
    health as health_mod,
)
from pci_planning_and_optimization import (
    logging_setup,
    metrics_prom,
    tracing,
)
from pci_planning_and_optimization.config import Config, load_config
from pci_planning_and_optimization.middleware import RecoveryMiddleware

__all__ = ["Orchestrator", "run"]


RAppMain = Callable[["Orchestrator"], Awaitable[None]]


class Orchestrator:

    __slots__ = (
        "_dashboard_task",
        "_extra_cleanup",
        "_uvicorn_server",
        "config",
        "fastapi_app",
        "health_manager",
        "host",
        "logger",
        "port",
        "registry",
        "shutdown_event",
    )

    def __init__(
        self,
        config: Config | None = None,
        *,
        fastapi_app: FastAPI | None = None,
        host: str = "0.0.0.0",
        port: int | None = None,
    ) -> None:
        self.config: Config = config or load_config()
        self.host = host
        self.port = port if port is not None else int(self.config.http_port)
        self.logger = logging_setup.with_component("main")
        self.registry = metrics_prom.get_registry()
        self.health_manager = health_mod.Manager(
            health_mod.Config(version="0.0.0")
        )
        self.fastapi_app: FastAPI = (
            fastapi_app
            if fastapi_app is not None
            else FastAPI(title="pci-planning-and-optimization")
        )
        self._dashboard_task: asyncio.Task[Any] | None = None
        self._uvicorn_server: uvicorn.Server | None = None
        self.shutdown_event: asyncio.Event = asyncio.Event()
        self._extra_cleanup: list[Callable[[], Awaitable[None]]] = []

    async def __aenter__(self) -> Orchestrator:
        await self.start()
        return self

    async def __aexit__(self, *_exc: object) -> None:
        await self.stop()

    async def start(self) -> None:
        self.logger.with_fields(
            {
                "log_level": self.config.log_level,
                "http_port": self.config.http_port,
            }
        ).debug("[STARTUP] Orchestrator booting")

        tracing.init(tracing.default_config())

        metrics_prom.register_default_runtime_collectors(self.registry)

        self._mount_infra_routes()
        self.fastapi_app.add_middleware(RecoveryMiddleware)



        self._dashboard_task = asyncio.create_task(
            self._run_dashboard_server(), name="dashboard-server"
        )

        self._install_signal_handlers()

        self.health_manager.set_startup_ready()
        self.logger.debug("[STARTUP] All infra ready")

