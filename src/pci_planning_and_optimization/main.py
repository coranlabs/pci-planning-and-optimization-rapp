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

    async def stop(self) -> None:
        self.logger.debug("[SHUTDOWN] Stopping orchestrator")
        self.health_manager.set_shutdown_mode()

        while self._extra_cleanup:
            cleanup = self._extra_cleanup.pop()
            with suppress(Exception):
                await cleanup()

        if self._uvicorn_server is not None:
            self._uvicorn_server.should_exit = True
        if self._dashboard_task is not None:
            with suppress(asyncio.CancelledError, Exception):
                await asyncio.wait_for(self._dashboard_task, timeout=10)

        self.logger.debug("[SHUTDOWN] Orchestrator stopped")

    def add_cleanup(self, coro_factory: Callable[[], Awaitable[None]]) -> None:
        self._extra_cleanup.append(coro_factory)

    def request_shutdown(self) -> None:
        self.shutdown_event.set()

    def _mount_infra_routes(self) -> None:
        probe_router = health_mod.health_router(self.health_manager)
        self.fastapi_app.include_router(probe_router)
        self.fastapi_app.include_router(
            metrics_prom.metrics_router(registry=self.registry)
        )

    async def _run_dashboard_server(self) -> None:
        cfg = uvicorn.Config(
            app=self.fastapi_app,
            host=self.host,
            port=self.port,
            log_level=self.config.log_level.lower(),
            access_log=False,
            log_config=None,
        )
        self._uvicorn_server = uvicorn.Server(cfg)
        await self._uvicorn_server.serve()

    def _install_signal_handlers(self) -> None:
        loop = asyncio.get_running_loop()
        for sig in (signal.SIGINT, signal.SIGTERM):
            with suppress(NotImplementedError, RuntimeError):
                loop.add_signal_handler(sig, self.request_shutdown)


async def _async_main(rapp_main: RAppMain | None = None) -> None:
    async with Orchestrator() as orch:
        if rapp_main is not None:
            user_task = asyncio.create_task(rapp_main(orch), name="rapp-main")
            try:
                await orch.shutdown_event.wait()
            finally:
                if not user_task.done():
                    user_task.cancel()
                    with suppress(asyncio.CancelledError, Exception):
                        await user_task
        else:
            orch.logger.warn(
                "[STARTUP] No rApp main coroutine registered; orchestrator "
                "will idle until SIGTERM. Pass rapp_main=callable to run() "
                "to plug the new rApp's main loop in."
            )
            await orch.shutdown_event.wait()


def run(rapp_main: RAppMain | None = None) -> None:
    asyncio.run(_async_main(rapp_main))


if __name__ == "__main__":
    run()
