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
import os
import time
from dataclasses import dataclass, field
from pathlib import Path
from types import TracebackType
from typing import TYPE_CHECKING, Any, Self
from urllib.parse import unquote, urlsplit

import asyncssh

from pci_planning_and_optimization.errors import AppError, new_sftp_error
from pci_planning_and_optimization.logging_setup import Logger, with_component
from pci_planning_and_optimization.tracing import (
    SpanKind,
    trace_sftp_download,
    with_span_kind,
)

_ = (SpanKind, with_span_kind)

if TYPE_CHECKING:
    from collections.abc import Sequence


__all__ = [
    "Config",
    "SFTPClient",
    "SFTPConnection",
]


_DEFAULT_MAX_IDLE_SECONDS: float = 5 * 60.0
_DEFAULT_CLEANUP_INTERVAL_SECONDS: float = 60.0
_DEFAULT_TIMEOUT_SECONDS: float = 30.0
_DEFAULT_PORT: int = 22

_DEFAULT_KEY_PATHS: tuple[str, ...] = (
    str(Path.home() / ".ssh" / "id_rsa"),
    str(Path.home() / ".ssh" / "id_ed25519"),
    "/root/.ssh/id_rsa",
    "/root/.ssh/id_ed25519",
)

_ENV_INSECURE_HOSTKEY = "RAPP_INSECURE_SSH_HOSTKEY"
_ENV_KNOWN_HOSTS_PATH = "RAPP_SSH_KNOWN_HOSTS"

_REDACTED = "redacted"


@dataclass(slots=True)
class Config:

    enabled: bool = False
    max_idle_seconds: float = _DEFAULT_MAX_IDLE_SECONDS
    cleanup_interval_seconds: float = _DEFAULT_CLEANUP_INTERVAL_SECONDS
    timeout_seconds: float = _DEFAULT_TIMEOUT_SECONDS

    def _apply_defaults(self) -> None:
        if self.max_idle_seconds <= 0:
            self.max_idle_seconds = _DEFAULT_MAX_IDLE_SECONDS
        if self.cleanup_interval_seconds <= 0:
            self.cleanup_interval_seconds = _DEFAULT_CLEANUP_INTERVAL_SECONDS
        if self.timeout_seconds <= 0:
            self.timeout_seconds = _DEFAULT_TIMEOUT_SECONDS


@dataclass(slots=True)
class SFTPConnection:

    ssh_conn: asyncssh.SSHClientConnection
    sftp_client: asyncssh.SFTPClient
    host: str
    last_used_monotonic: float = field(default_factory=time.monotonic)
    lock: asyncio.Lock = field(default_factory=asyncio.Lock)


class SFTPClient:

    __slots__ = (
        "_cleanup_task",
        "_config",
        "_connection_pool",
        "_insecure_hostkey",
        "_known_hosts_path",
        "_logger",
        "_pool_lock",
    )

    def __init__(self, logger: Logger | None, config: Config) -> None:
        base = logger if logger is not None else with_component("sftp")
        self._logger: Logger = base.with_component("sftp")

        cfg = Config(
            enabled=config.enabled,
            max_idle_seconds=config.max_idle_seconds,
            cleanup_interval_seconds=config.cleanup_interval_seconds,
            timeout_seconds=config.timeout_seconds,
        )
        cfg._apply_defaults()
        self._config: Config = cfg

        self._connection_pool: dict[str, SFTPConnection] = {}
        self._pool_lock: asyncio.Lock = asyncio.Lock()

        self._insecure_hostkey: bool = _read_insecure_flag()
        self._known_hosts_path: str = _resolve_known_hosts_path()

        if self._insecure_hostkey:
            self._logger.with_field(
                "env", _ENV_INSECURE_HOSTKEY
            ).warn(
                "[SFTP] Host-key verification DISABLED via "
                f"{_ENV_INSECURE_HOSTKEY}=1. Any presented host key is "
                "accepted, so a man-in-the-middle is undetectable."
            )

        self._cleanup_task: asyncio.Task[None] | None = None
        if cfg.enabled:
            try:
                self._cleanup_task = asyncio.get_running_loop().create_task(
                    self._cleanup_idle_connections(),
                    name="sftp-idle-cleanup",
                )
            except RuntimeError:
                self._cleanup_task = None

