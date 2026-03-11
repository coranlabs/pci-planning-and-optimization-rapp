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

    def ensure_started(self) -> None:
        if not self._config.enabled or self._cleanup_task is not None:
            return
        self._cleanup_task = asyncio.get_running_loop().create_task(
            self._cleanup_idle_connections(),
            name="sftp-idle-cleanup",
        )

    def is_enabled(self) -> bool:
        return self._config.enabled

    async def fetch_file(self, file_url: str) -> bytes:
        if not self._config.enabled:
            raise new_sftp_error(
                "DISABLED",
                "SFTP client is disabled",
                None,
            )

        host, username, password, filepath = _parse_sftp_url(file_url)

        self._logger.with_fields(
            {"host": host, "path": filepath, "user": username, "credential": _REDACTED}
        ).debug("[SFTP] Fetching file")

        conn = await self._get_connection(host, username, password)

        start = time.monotonic()
        with trace_sftp_download(host, filepath, 0):
            try:
                data = await self._download_file(conn, filepath)
            except AppError:
                await self._close_connection(host)
                raise
            except BaseException as exc:
                await self._close_connection(host)
                raise new_sftp_error(
                    "DOWNLOAD",
                    f"failed to download file: {filepath}",
                    exc,
                ) from exc

        duration_seconds = time.monotonic() - start
        self._logger.with_fields(
            {
                "path": filepath,
                "size": len(data),
                "duration_seconds": duration_seconds,
            }
        ).debug("[SFTP] File fetched successfully")

        return data

    async def aclose(self) -> None:
        if self._cleanup_task is not None and not self._cleanup_task.done():
            self._cleanup_task.cancel()
            try:
                await self._cleanup_task
            except (asyncio.CancelledError, BaseException):
                pass
        self._cleanup_task = None

        async with self._pool_lock:
            hosts = list(self._connection_pool.keys())
            for host in hosts:
                conn = self._connection_pool.pop(host)
                await _safe_close(conn, self._logger, host)
            self._connection_pool.clear()

        self._logger.info("[SFTP] All connections closed")

    async def __aenter__(self) -> Self:
        self.ensure_started()
        return self

    async def __aexit__(
        self,
        exc_type: type[BaseException] | None,
        exc: BaseException | None,
        tb: TracebackType | None,
    ) -> None:
        await self.aclose()

    async def _get_connection(
        self, host: str, username: str, password: str
    ) -> SFTPConnection:
        async with self._pool_lock:
            conn = self._connection_pool.get(host)
            if conn is not None:
                async with conn.lock:
                    if await self._is_connection_alive(conn):
                        conn.last_used_monotonic = time.monotonic()
                        self._logger.with_field("host", host).debug(
                            "[SFTP] Reusing existing connection"
                        )
                        return conn

                self._logger.with_field("host", host).warn(
                    "[SFTP] Connection dead, creating new one"
                )
                await _safe_close(conn, self._logger, host)
                self._connection_pool.pop(host, None)

            self._logger.with_field("host", host).debug(
                "[SFTP] Creating new connection"
            )
            new_conn = await self._create_connection(host, username, password)
            self._connection_pool[host] = new_conn
            self._logger.with_field("host", host).info(
                "[SFTP] Connection established"
            )
            return new_conn

    async def _create_connection(
        self, host: str, username: str, password: str
    ) -> SFTPConnection:
        ssh_host, ssh_port = _split_host_port(host)

        client_keys: list[str] = []
        for key_path in _DEFAULT_KEY_PATHS:
            try:
                if os.path.isfile(key_path) and os.access(key_path, os.R_OK):
                    client_keys.append(key_path)
                    self._logger.with_field("keyFile", key_path).debug(
                        "[SFTP] Using SSH key authentication"
                    )
                    break
            except OSError:
                continue

        has_password = bool(password)
        if not client_keys and not has_password:
            raise new_sftp_error(
                "NO_AUTH",
                "no authentication methods available "
                "(no SSH key found and no password provided)",
                None,
            )

        connect_kwargs: dict[str, Any] = {
            "host": ssh_host,
            "port": ssh_port,
            "username": username,
            "connect_timeout": self._config.timeout_seconds,
        }
        if client_keys:
            connect_kwargs["client_keys"] = client_keys
        else:
            connect_kwargs["client_keys"] = None
        if has_password:
            connect_kwargs["password"] = password

        if self._insecure_hostkey:
            connect_kwargs["known_hosts"] = None
        else:
            kh_path = self._known_hosts_path
            if not os.path.isfile(kh_path):
                raise new_sftp_error(
                    "KNOWN_HOSTS_MISSING",
                    (
                        f"host-key verification is ON but {kh_path} is "
                        f"missing. Either create it (ssh-keyscan {ssh_host} "
                        f">> {kh_path}) or set {_ENV_INSECURE_HOSTKEY}=1 "
                        "to bypass (insecure, matches Go default)."
                    ),
                    None,
                )
            connect_kwargs["known_hosts"] = kh_path

        try:
            ssh_conn = await asyncio.wait_for(
                asyncssh.connect(**connect_kwargs),
                timeout=self._config.timeout_seconds,
            )
        except AppError:
            raise
        except TimeoutError as exc:
            raise new_sftp_error(
                "CONN_TIMEOUT",
                f"timed out dialing SSH to {host}",
                exc,
            ) from exc
        except (asyncssh.PermissionDenied, asyncssh.DisconnectError) as exc:
            raise new_sftp_error(
                "AUTH",
                f"SSH authentication failed for {username}@{host}",
                exc,
            ) from exc
        except BaseException as exc:
            raise new_sftp_error(
                "CONN",
                f"failed to dial SSH to {host}",
                exc,
            ) from exc

        try:
            sftp_client = await ssh_conn.start_sftp_client()
        except BaseException as exc:
            try:
                ssh_conn.close()
                await ssh_conn.wait_closed()
            except BaseException:
                pass
            raise new_sftp_error(
                "SFTP_CHANNEL",
                f"failed to start SFTP subsystem on {host}",
                exc,
            ) from exc

        return SFTPConnection(
            ssh_conn=ssh_conn,
            sftp_client=sftp_client,
            host=host,
            last_used_monotonic=time.monotonic(),
        )

    async def _download_file(
        self, conn: SFTPConnection, filepath: str
    ) -> bytes:
        async with conn.lock:
            try:
                remote = await conn.sftp_client.open(filepath, "rb")
            except asyncssh.SFTPNoSuchFile as exc:
                raise new_sftp_error(
                    "OPEN",
                    f"remote file not found: {filepath}",
                    exc,
                ) from exc
            except asyncssh.SFTPError as exc:
                raise new_sftp_error(
                    "OPEN",
                    f"failed to open remote file: {filepath}",
                    exc,
                ) from exc

            try:
                data = await remote.read()
                if isinstance(data, str):
                    data = data.encode("utf-8")
            except BaseException as exc:
                raise new_sftp_error(
                    "READ",
                    f"failed to read remote file: {filepath}",
                    exc,
                ) from exc
            finally:
                try:
                    await remote.close()
                except BaseException:
                    pass

            conn.last_used_monotonic = time.monotonic()
            return data

    async def _is_connection_alive(self, conn: SFTPConnection) -> bool:
        try:
            await conn.sftp_client.stat("/")
        except BaseException:
            return False
        return True

    async def _close_connection(self, host: str) -> None:
        async with self._pool_lock:
            conn = self._connection_pool.pop(host, None)
            if conn is not None:
                await _safe_close(conn, self._logger, host)

    async def _cleanup_idle_connections(self) -> None:
        interval = self._config.cleanup_interval_seconds
        try:
            while True:
                await asyncio.sleep(interval)
                now = time.monotonic()
                async with self._pool_lock:
                    stale_hosts: list[str] = []
                    for host, conn in self._connection_pool.items():
                        idle_seconds = now - conn.last_used_monotonic
                        if idle_seconds > self._config.max_idle_seconds:
                            stale_hosts.append(host)
                            self._logger.with_fields(
                                {"host": host, "idle_seconds": idle_seconds}
                            ).debug("[SFTP] Cleaning up idle connection")
                    for host in stale_hosts:
                        conn = self._connection_pool.pop(host, None)
                        if conn is not None:
                            await _safe_close(conn, self._logger, host)
        except asyncio.CancelledError:
            raise


