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
import inspect
import json
import time
from collections.abc import Awaitable, Callable, Mapping
from dataclasses import dataclass, field
from datetime import UTC, datetime
from enum import StrEnum
from typing import Any, Union

from fastapi import APIRouter, Request, Response

from pci_planning_and_optimization.logging_setup import Logger, with_component


class Status(StrEnum):
    HEALTHY = "healthy"
    UNHEALTHY = "unhealthy"
    DEGRADED = "degraded"
    UNKNOWN = "unknown"


STATUS_HEALTHY: Status = Status.HEALTHY
STATUS_UNHEALTHY: Status = Status.UNHEALTHY
STATUS_DEGRADED: Status = Status.DEGRADED
STATUS_UNKNOWN: Status = Status.UNKNOWN


def _now_utc() -> datetime:
    return datetime.now(UTC)


def _format_rfc3339_nano(ts: datetime) -> str:
    if ts.tzinfo is None:
        ts = ts.replace(tzinfo=UTC)
    base = ts.strftime("%Y-%m-%dT%H:%M:%S")
    nanos = f"{ts.microsecond:06d}000"
    return f"{base}.{nanos}Z"


def _format_uptime(start: float) -> str:
    delta = max(0, round(time.monotonic() - start))
    if delta == 0:
        return "0s"
    hours, rem = divmod(delta, 3600)
    minutes, seconds = divmod(rem, 60)
    out = ""
    if hours:
        out += f"{hours}h"
    if minutes or hours:
        out += f"{minutes}m"
    out += f"{seconds}s"
    return out


@dataclass
class ComponentHealth:

    status: Status = Status.UNKNOWN
    name: str = ""
    message: str = ""
    last_checked: datetime | None = None
    details: dict[str, Any] | None = None

    def to_dict(self) -> dict[str, Any]:
        out: dict[str, Any] = {
            "name": self.name,
            "status": str(self.status),
        }
        if self.message:
            out["message"] = self.message
        out["last_checked"] = (
            _format_rfc3339_nano(self.last_checked)
            if self.last_checked is not None
            else "0001-01-01T00:00:00Z"
        )
        if self.details:
            out["details"] = self.details
        return out


@dataclass
class HealthResponse:

    status: Status = Status.UNKNOWN
    timestamp: datetime = field(default_factory=_now_utc)
    components: dict[str, ComponentHealth] = field(default_factory=dict)
    version: str = ""
    uptime: str = ""

    def to_dict(self) -> dict[str, Any]:
        out: dict[str, Any] = {
            "status": str(self.status),
            "timestamp": _format_rfc3339_nano(self.timestamp),
        }
        if self.components:
            out["components"] = {n: c.to_dict() for n, c in self.components.items()}
        if self.version:
            out["version"] = self.version
        if self.uptime:
            out["uptime"] = self.uptime
        return out


SyncChecker = Callable[[], ComponentHealth]
AsyncChecker = Callable[[], Awaitable[ComponentHealth]]
Checker = Union[SyncChecker, AsyncChecker]


@dataclass
class Config:

    version: str = "unknown"
    cache_ttl: float = 5.0
    check_timeout: float = 10.0


def default_config() -> Config:
    return Config(version="unknown", cache_ttl=5.0, check_timeout=10.0)


def _encode_go_json(payload: Any) -> bytes:
    text = json.dumps(
        payload,
        ensure_ascii=False,
        separators=(",", ":"),
    )
    text = text.replace("<", "\\u003c").replace(">", "\\u003e").replace("&", "\\u0026")
    return (text + "\n").encode("utf-8")


def _json_response(payload: Any, status_code: int) -> Response:
    return Response(
        content=_encode_go_json(payload),
        status_code=status_code,
        media_type="application/json",
    )


class Manager:

    def __init__(self, cfg: Config | None = None, logger: Logger | None = None) -> None:
        if cfg is None:
            cfg = default_config()
        self._cfg = cfg
        self._logger: Logger = logger if logger is not None else with_component("health")

        self._checkers: dict[str, Checker] = {}
        self._mu = asyncio.Lock()

        self._cache: dict[str, ComponentHealth] = {}
        self._last_check_mono: float = 0.0
        self._check_mu = asyncio.Lock()

        self._startup_ready: bool = False
        self._shutdown_mode: bool = False

        self._start_mono: float = time.monotonic()
        self._version: str = cfg.version
        self._cache_ttl: float = cfg.cache_ttl
        self._check_timeout: float = cfg.check_timeout

    async def register_checker(self, name: str, checker: Checker) -> None:
        async with self._mu:
            self._checkers[name] = checker
        self._logger.infof("[HEALTH] Registered health checker for component: %s", name)

    def register_checker_sync(self, name: str, checker: Checker) -> None:
        self._checkers[name] = checker
        self._logger.infof("[HEALTH] Registered health checker for component: %s", name)

    async def unregister_checker(self, name: str) -> bool:
        async with self._mu:
            return self._checkers.pop(name, None) is not None

    def set_startup_ready(self) -> None:
        self._startup_ready = True
        self._logger.info("[HEALTH] Application marked as startup ready")

    def set_shutdown_mode(self) -> None:
        self._shutdown_mode = True
        self._logger.info("[HEALTH] Application entering shutdown mode")

    def is_startup_ready(self) -> bool:
        return self._startup_ready

    def is_shutting_down(self) -> bool:
        return self._shutdown_mode

    async def _run_checker(self, name: str, checker: Checker) -> ComponentHealth:
        try:
            if inspect.iscoroutinefunction(checker):
                coro: Awaitable[ComponentHealth] = checker()
            else:
                coro = asyncio.to_thread(checker)
            health = await asyncio.wait_for(coro, timeout=self._check_timeout)
        except TimeoutError:
            self._logger.warnf(
                "[HEALTH] Checker %s timed out after %ss", name, self._check_timeout
            )
            health = ComponentHealth(
                status=Status.UNHEALTHY,
                message=f"health check timed out after {self._check_timeout}s",
            )
        except Exception as exc:
            self._logger.with_error(exc).errorf(
                "[HEALTH] Checker %s raised an exception", name
            )
            health = ComponentHealth(
                status=Status.UNHEALTHY,
                message=f"health check raised: {exc}",
            )
        health.name = name
        health.last_checked = _now_utc()
        return health

    async def check_health(self) -> HealthResponse:
        async with self._check_mu:
            now_mono = time.monotonic()
            if (now_mono - self._last_check_mono) < self._cache_ttl and self._cache:
                return self._build_response(self._cache)

            async with self._mu:
                checkers_snapshot = dict(self._checkers)

            if not checkers_snapshot:
                self._cache = {}
                self._last_check_mono = time.monotonic()
                return self._build_response({})

            tasks = [
                asyncio.create_task(self._run_checker(name, c), name=f"hc:{name}")
                for name, c in checkers_snapshot.items()
            ]
            done = await asyncio.gather(*tasks, return_exceptions=False)
            results: dict[str, ComponentHealth] = {
                ch.name: ch for ch in done
            }

            self._cache = results
            self._last_check_mono = time.monotonic()

            return self._build_response(results)

    def _build_response(
        self, components: Mapping[str, ComponentHealth]
    ) -> HealthResponse:
        overall = Status.HEALTHY
        has_unhealthy = False
        has_degraded = False
        for c in components.values():
            if c.status == Status.UNHEALTHY:
                has_unhealthy = True
            elif c.status == Status.DEGRADED:
                has_degraded = True
        if has_unhealthy:
            overall = Status.UNHEALTHY
        elif has_degraded:
            overall = Status.DEGRADED

        return HealthResponse(
            status=overall,
            timestamp=_now_utc(),
            components=dict(components),
            version=self._version,
            uptime=_format_uptime(self._start_mono),
        )

    def liveness_payload(self) -> tuple[dict[str, str], int]:
        return {"status": "alive"}, 200

    def readiness_payload(self) -> tuple[dict[str, str], int]:
        if self.is_shutting_down():
            return {"status": "shutting_down"}, 503
        if not self.is_startup_ready():
            return {"status": "not_ready"}, 503
        return {"status": "ready"}, 200

    def startup_payload(self) -> tuple[dict[str, str], int]:
        if not self.is_startup_ready():
            return {"status": "starting"}, 503
        return {"status": "started"}, 200

    def handle_liveness_probe(self) -> Response:
        payload, code = self.liveness_payload()
        return _json_response(payload, code)

    def handle_readiness_probe(self) -> Response:
        payload, code = self.readiness_payload()
        return _json_response(payload, code)

    def handle_startup_probe(self) -> Response:
        payload, code = self.startup_payload()
        return _json_response(payload, code)

    def liveness_handler_response(self) -> Response:
        payload = {
            "status": "alive",
            "timestamp": _format_rfc3339_nano(_now_utc()),
            "uptime": _format_uptime(self._start_mono),
        }
        return _json_response(payload, 200)

    async def readiness_handler_response(self) -> Response:
        if not self.is_startup_ready():
            return _json_response(
                {
                    "status": "not_ready",
                    "reason": "startup_incomplete",
                    "message": "Application is still starting up",
                },
                503,
            )
        if self.is_shutting_down():
            return _json_response(
                {
                    "status": "not_ready",
                    "reason": "shutting_down",
                    "message": "Application is shutting down",
                },
                503,
            )
        resp = await self.check_health()
        code = 503 if resp.status == Status.UNHEALTHY else 200
        payload: dict[str, Any] = {
            "status": str(resp.status),
            "timestamp": _format_rfc3339_nano(resp.timestamp),
            "components": {n: c.to_dict() for n, c in resp.components.items()},
        }
        return _json_response(payload, code)

    def startup_handler_response(self) -> Response:
        if self.is_startup_ready():
            payload = {
                "status": "started",
                "timestamp": _format_rfc3339_nano(_now_utc()),
                "uptime": _format_uptime(self._start_mono),
            }
            return _json_response(payload, 200)
        return _json_response(
            {"status": "starting", "message": "Application is initializing"},
            503,
        )

    async def full_health_handler_response(self) -> Response:
        resp = await self.check_health()
        if resp.status == Status.HEALTHY or resp.status == Status.DEGRADED:
            code = 200
        elif resp.status == Status.UNHEALTHY:
            code = 503
        else:
            code = 500
        return _json_response(resp.to_dict(), code)


def kafka_checker(
    is_connected: Callable[[], bool],
    in_flight_count: Callable[[], int],
) -> AsyncChecker:

    async def _checker() -> ComponentHealth:
        connected = bool(is_connected())
        in_flight = int(in_flight_count())
        status = Status.HEALTHY
        message = "Kafka consumer is connected"
        if not connected:
            status = Status.UNHEALTHY
            message = "Kafka consumer is disconnected"
        return ComponentHealth(
            status=status,
            message=message,
            details={
                "connected": connected,
                "in_flight_count": in_flight,
            },
        )

    return _checker


def influxdb_checker(
    ping: Callable[[], Awaitable[None]] | Callable[[], None],
) -> AsyncChecker:

    async def _checker() -> ComponentHealth:
        try:
            result = ping()
            if inspect.isawaitable(result):
                await result
        except Exception as exc:
            return ComponentHealth(
                status=Status.UNHEALTHY,
                message=f"InfluxDB ping failed: {exc}",
            )
        return ComponentHealth(
            status=Status.HEALTHY,
            message="InfluxDB is reachable",
        )

    return _checker


def sftp_checker(
    get_pool_stats: Callable[[], Mapping[str, Any]],
) -> AsyncChecker:

    async def _checker() -> ComponentHealth:
        stats = dict(get_pool_stats() or {})
        active_raw = stats.get("active_connections", 0)
        total_raw = stats.get("total_connections", 0)
        active = int(active_raw) if isinstance(active_raw, (int, float)) else 0
        total = int(total_raw) if isinstance(total_raw, (int, float)) else 0

        status = Status.HEALTHY
        message = "SFTP pool is healthy"
        if total > 0 and (active / total) > 0.9:
            status = Status.DEGRADED
            message = "SFTP pool is heavily utilized"

        return ComponentHealth(status=status, message=message, details=stats)

    return _checker


def dlq_checker(
    get_stats: Callable[[], Mapping[str, Any]],
) -> AsyncChecker:

    async def _checker() -> ComponentHealth:
        stats = dict(get_stats() or {})

        enabled_raw = stats.get("enabled", False)
        enabled = bool(enabled_raw) if isinstance(enabled_raw, bool) else False
        if not enabled:
            return ComponentHealth(status=Status.HEALTHY, message="DLQ is disabled")

        total_raw = stats.get("total_messages", 0)
        perm_raw = stats.get("permanent_failure", 0)
        max_raw = stats.get("max_size", 10000)

        total = int(total_raw) if isinstance(total_raw, (int, float)) else 0
        permanent = int(perm_raw) if isinstance(perm_raw, (int, float)) else 0
        max_size = int(max_raw) if isinstance(max_raw, (int, float)) else 10000

        status = Status.HEALTHY
        message = "DLQ is operating normally"
        if permanent > 100:
            status = Status.DEGRADED
            message = "DLQ has many permanent failures, manual intervention may be needed"
        if max_size > 0 and (total / max_size) > 0.8:
            status = Status.DEGRADED
            message = "DLQ is filling up"

        return ComponentHealth(status=status, message=message, details=stats)

    return _checker


def circuit_breaker_checker(
    get_stats: Callable[[], Mapping[str, Any]],
) -> AsyncChecker:

    async def _checker() -> ComponentHealth:
        stats = dict(get_stats() or {})
        open_circuits = 0
        for v in stats.values():
            if isinstance(v, Mapping):
                state = v.get("state")
                if isinstance(state, str) and state == "open":
                    open_circuits += 1
        status = Status.HEALTHY
        message = "All circuit breakers are closed"
        if open_circuits > 0:
            status = Status.DEGRADED
            message = "Some circuit breakers are open"
        return ComponentHealth(
            status=status,
            message=message,
            details={
                "open_circuits": open_circuits,
                "circuits": stats,
            },
        )

    return _checker


KafkaChecker = kafka_checker
InfluxDBChecker = influxdb_checker
SFTPChecker = sftp_checker
DLQChecker = dlq_checker
CircuitBreakerChecker = circuit_breaker_checker


def health_router(manager: Manager) -> APIRouter:
    router = APIRouter(tags=["health"])

    @router.get("/healthz", include_in_schema=True)
    async def healthz(_request: Request) -> Response:
        return manager.handle_liveness_probe()

    @router.get("/readyz", include_in_schema=True)
    async def readyz(_request: Request) -> Response:
        return manager.handle_readiness_probe()

    @router.get("/startupz", include_in_schema=True)
    async def startupz(_request: Request) -> Response:
        return manager.handle_startup_probe()

    return router


__all__ = [
    "STATUS_DEGRADED",
    "STATUS_HEALTHY",
    "STATUS_UNHEALTHY",
    "STATUS_UNKNOWN",
    "AsyncChecker",
    "Checker",
    "CircuitBreakerChecker",
    "ComponentHealth",
    "Config",
    "DLQChecker",
    "HealthResponse",
    "InfluxDBChecker",
    "KafkaChecker",
    "Manager",
    "SFTPChecker",
    "Status",
    "SyncChecker",
    "circuit_breaker_checker",
    "default_config",
    "dlq_checker",
    "health_router",
    "influxdb_checker",
    "kafka_checker",
    "sftp_checker",
]
