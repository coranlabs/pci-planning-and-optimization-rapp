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
import threading
import time
from collections.abc import Awaitable, Callable
from typing import Any

from pydantic import BaseModel, ConfigDict, Field

from pci_planning_and_optimization.errors import ERR_RATE_LIMITED
from pci_planning_and_optimization.logging_setup import Logger, with_component

_Clock = Callable[[], float]
_Sleeper = Callable[[float], Awaitable[None]]

_clock: _Clock = time.monotonic
_sleeper: _Sleeper = asyncio.sleep


def set_clock(clock: _Clock) -> None:
    global _clock
    _clock = clock


def set_sleeper(sleeper: _Sleeper) -> None:
    global _sleeper
    _sleeper = sleeper


def _now() -> float:
    return _clock()


class RateLimiterConfig(BaseModel):

    model_config = ConfigDict(populate_by_name=True, frozen=True)

    requests_per_second: float = Field(
        default=10.0,
        gt=0.0,
        alias="requests_per_second",
        description="Sustained admit rate.",
    )
    burst_size: int = Field(
        default=20,
        gt=0,
        alias="burst_size",
        description="Maximum tokens the bucket can hold.",
    )
    wait_timeout: float = Field(
        default=30.0,
        ge=0.0,
        alias="wait_timeout",
        description=(
            "Seconds ``acquire`` may block before raising "
            "ERR_RATE_LIMITED. 0 disables the timeout."
        ),
    )


def default_config() -> RateLimiterConfig:
    return RateLimiterConfig()


class RateLimiter:

    __slots__ = (
        "_async_lock",
        "_config",
        "_last_update",
        "_name",
        "_thread_lock",
        "_tokens",
    )

    def __init__(self, name: str, config: RateLimiterConfig) -> None:
        self._config = config
        self._name = name
        self._tokens: float = float(config.burst_size)
        self._last_update: float = _now()
        self._thread_lock = threading.Lock()
        self._async_lock = asyncio.Lock()

    @property
    def name(self) -> str:
        return self._name

    @property
    def config(self) -> RateLimiterConfig:
        return self._config

    @property
    def last_update(self) -> float:
        return self._last_update

    def _refill_locked(self) -> None:
        now = _now()
        elapsed = now - self._last_update
        self._last_update = now
        self._tokens += elapsed * self._config.requests_per_second
        burst = float(self._config.burst_size)
        if self._tokens > burst:
            self._tokens = burst

    def try_acquire(self) -> bool:
        with self._thread_lock:
            self._refill_locked()
            if self._tokens >= 1.0:
                self._tokens -= 1.0
                return True
            return False

    def allow(self) -> bool:
        return self.try_acquire()

    async def acquire(self, timeout: float | None = None) -> None:
        effective_timeout = (
            self._config.wait_timeout if timeout is None else timeout
        )
        deadline: float | None = None
        if effective_timeout > 0:
            deadline = _now() + effective_timeout

        async with self._async_lock:
            while True:
                wait_time: float
                with self._thread_lock:
                    self._refill_locked()
                    if self._tokens >= 1.0:
                        self._tokens -= 1.0
                        return
                    tokens_needed = 1.0 - self._tokens
                    wait_time = (
                        tokens_needed / self._config.requests_per_second
                    ) + 0.001

                if deadline is not None:
                    remaining = deadline - _now()
                    if remaining <= 0:
                        _log_rate_limited(self._name)
                        raise ERR_RATE_LIMITED.with_context(
                            "limiter", self._name
                        ).with_context("wait_timeout_s", effective_timeout)
                    if wait_time > remaining:
                        wait_time = remaining

                await _sleeper(wait_time)

    def tokens(self) -> float:
        with self._thread_lock:
            self._refill_locked()
            return self._tokens

    def stats(self) -> dict[str, Any]:
        with self._thread_lock:
            self._refill_locked()
            return {
                "name": self._name,
                "available_tokens": self._tokens,
                "burst_size": self._config.burst_size,
                "requests_per_second": self._config.requests_per_second,
            }


def _component_logger() -> Logger:
    return with_component("ratelimit")


def _log_created(key: str, config: RateLimiterConfig) -> None:
    _component_logger().infof(
        "[RATELIMIT] Created new rate limiter for %s (rate: %.2f/s, burst: %d)",
        key,
        config.requests_per_second,
        config.burst_size,
    )


def _log_cleanup(removed: int) -> None:
    _component_logger().infof(
        "[RATELIMIT] Cleanup: removed %d idle limiters", removed
    )


def _log_rate_limited(key: str) -> None:
    _component_logger().warnf(
        "[RATELIMIT] Wait timeout exceeded for %s; raising ERR_RATE_LIMITED",
        key,
    )


class RateLimiterManager:

    __slots__ = ("_config", "_limiters", "_lock")

    def __init__(self, default_config: RateLimiterConfig | None = None) -> None:
        self._config = default_config if default_config is not None else RateLimiterConfig()
        self._limiters: dict[str, RateLimiter] = {}
        self._lock = threading.RLock()

    @property
    def config(self) -> RateLimiterConfig:
        return self._config

    def get_or_create(self, key: str) -> RateLimiter:
        with self._lock:
            existing = self._limiters.get(key)
            if existing is not None:
                return existing
            limiter = RateLimiter(key, self._config)
            self._limiters[key] = limiter
            _log_created(key, self._config)
            return limiter

    def allow(self, key: str) -> bool:
        return self.get_or_create(key).try_acquire()

    async def wait(self, key: str, timeout: float | None = None) -> None:
        await self.get_or_create(key).acquire(timeout=timeout)

    def stats(self) -> dict[str, Any]:
        with self._lock:
            return {key: limiter.stats() for key, limiter in self._limiters.items()}

    def cleanup(self, max_idle: float) -> int:
        cutoff = _now() - max_idle
        removed = 0
        with self._lock:
            for key in list(self._limiters.keys()):
                limiter = self._limiters[key]
                if limiter.last_update < cutoff:
                    del self._limiters[key]
                    removed += 1
        if removed > 0:
            _log_cleanup(removed)
        return removed

    def __len__(self) -> int:
        with self._lock:
            return len(self._limiters)

    def __contains__(self, key: object) -> bool:
        with self._lock:
            return key in self._limiters


_global_manager: RateLimiterManager | None = None
_global_lock = threading.Lock()


def global_manager() -> RateLimiterManager:
    global _global_manager
    if _global_manager is None:
        with _global_lock:
            if _global_manager is None:
                _global_manager = RateLimiterManager(default_config())
    return _global_manager


def reset_global_manager() -> None:
    global _global_manager
    with _global_lock:
        _global_manager = None


KeyFunc = Callable[[Any], str]


def _default_key(request: Any) -> str:
    client = getattr(request, "client", None)
    if client is not None:
        host = getattr(client, "host", None)
        if host:
            return str(host)
    return "anonymous"


def rate_limit_dependency(
    manager: RateLimiterManager | None = None,
    *,
    key_func: KeyFunc | None = None,
    block: bool = False,
    timeout: float | None = None,
) -> Callable[[Any], Awaitable[None]]:
    chosen_key = key_func if key_func is not None else _default_key

    async def _dependency(request: Any) -> None:
        active = manager if manager is not None else global_manager()
        key = chosen_key(request)
        if block:
            await active.wait(key, timeout=timeout)
            return
        if not active.allow(key):
            _log_rate_limited(key)
            raise ERR_RATE_LIMITED.with_context("limiter", key)

    return _dependency


__all__ = [
    "KeyFunc",
    "RateLimiter",
    "RateLimiterConfig",
    "RateLimiterManager",
    "default_config",
    "global_manager",
    "rate_limit_dependency",
    "reset_global_manager",
    "set_clock",
    "set_sleeper",
]
