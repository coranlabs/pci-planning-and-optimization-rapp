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

