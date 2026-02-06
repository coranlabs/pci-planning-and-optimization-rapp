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
from enum import StrEnum
from typing import Any, TypeVar

from pydantic import BaseModel, ConfigDict, Field

from pci_planning_and_optimization.errors import (
    ERR_CIRCUIT_OPEN,
    AppError,
    ErrorCategory,
    new,
    wrap,
)
from pci_planning_and_optimization.logging_setup import Logger, with_component

_monotonic: Callable[[], float] = time.monotonic


try:
    from pybreaker import CircuitBreakerError as _PyBreakerError
except ImportError:
    _PyBreakerError = Exception


T = TypeVar("T")


ErrCircuitOpen: AppError = ERR_CIRCUIT_OPEN

ErrTooManyRequests: AppError = new(
    ErrorCategory.RATE_LIMIT,
    "SVC_CB_TOO_MANY_REQUESTS",
    "too many requests in half-open state",
)

ErrServiceUnavailable: AppError = new(
    ErrorCategory.UNAVAILABLE,
    "SVC_UNAVAILABLE",
    "service temporarily unavailable",
)


class CircuitOpenError(_PyBreakerError):

    def __init__(self, app_error: AppError) -> None:
        super().__init__(str(app_error))
        self.app_error = app_error
        self.__cause__ = app_error


class State(StrEnum):
    CLOSED = "closed"
    HALF_OPEN = "half-open"
    OPEN = "open"


class Counts(BaseModel):

    model_config = ConfigDict(populate_by_name=True)

    requests: int = Field(default=0, ge=0, alias="requests")
    total_successes: int = Field(default=0, ge=0, alias="total_successes")
    total_failures: int = Field(default=0, ge=0, alias="total_failures")
    consecutive_successes: int = Field(default=0, ge=0, alias="consecutive_successes")
    consecutive_failures: int = Field(default=0, ge=0, alias="consecutive_failures")

    def on_request(self) -> None:
        self.requests += 1

    def on_success(self) -> None:
        self.total_successes += 1
        self.consecutive_successes += 1
        self.consecutive_failures = 0

    def on_failure(self) -> None:
        self.total_failures += 1
        self.consecutive_failures += 1
        self.consecutive_successes = 0

    def clear(self) -> None:
        self.requests = 0
        self.total_successes = 0
        self.total_failures = 0
        self.consecutive_successes = 0
        self.consecutive_failures = 0


StateChangeCallback = Callable[[str, str, str], None]


class Config(BaseModel):

    model_config = ConfigDict(arbitrary_types_allowed=True)

    name: str = Field(description="Identifier for the circuit breaker")
    max_requests: int = Field(
        default=3,
        ge=1,
        description="Max test requests allowed in half-open state",
    )
    interval: float = Field(
        default=60.0,
        ge=0.0,
        description="Seconds between count clears in closed state. "
        "Zero disables periodic reset.",
    )
    timeout: float = Field(
        default=30.0,
        gt=0.0,
        description="Seconds to stay in open state before transitioning to "
        "half-open",
    )
    failure_ratio: float = Field(
        default=0.6,
        ge=0.0,
        le=1.0,
        description="Trip the breaker once this fraction of requests fail "
        "in the current window",
    )
    min_requests: int = Field(
        default=5,
        ge=0,
        description="Minimum requests in the window before the failure ratio "
        "is evaluated",
    )
    on_state_change: StateChangeCallback | None = Field(
        default=None,
        description="Optional callback invoked on every state transition "
        "with (name, from_state, to_state).",
    )


def default_config(name: str) -> Config:
    return Config(
        name=name,
        max_requests=3,
        interval=60.0,
        timeout=30.0,
        failure_ratio=0.6,
        min_requests=5,
        on_state_change=None,
    )


_log: Logger = with_component("circuit-breaker")


class Breaker:

    __slots__ = (
        "_async_lock",
        "_config",
        "_counts",
        "_expiry",
        "_generation",
        "_state",
        "_sync_lock",
    )

    def __init__(self, config: Config) -> None:
        self._config = config
        self._state: State = State.CLOSED
        self._counts: Counts = Counts()
        self._expiry: float = self._compute_initial_expiry()
        self._generation: int = 0
        self._sync_lock = threading.RLock()
        self._async_lock = asyncio.Lock()

    @property
    def name(self) -> str:
        return self._config.name

    @property
    def config(self) -> Config:
        return self._config

    def state(self) -> State:
        with self._sync_lock:
            now = _monotonic()
            state, _ = self._current_state(now)
            return state

    def counts(self) -> Counts:
        with self._sync_lock:
            return self._counts.model_copy()

    def is_open(self) -> bool:
        return self.state() == State.OPEN

    def is_closed(self) -> bool:
        return self.state() == State.CLOSED

    def is_half_open(self) -> bool:
        return self.state() == State.HALF_OPEN

    def execute(self, fn: Callable[..., T], *args: Any, **kwargs: Any) -> T:
        generation = self._before_call()
        try:
            result = fn(*args, **kwargs)
        except BaseException as exc:
            self._after_call(generation, success=False)
            raise exc
        self._after_call(generation, success=True)
        return result

    async def execute_async(
        self,
        fn: Callable[..., Awaitable[T]],
        *args: Any,
        **kwargs: Any,
    ) -> T:
        async with self._async_lock:
            generation = self._before_call()
        try:
            result = await fn(*args, **kwargs)
        except BaseException as exc:
            async with self._async_lock:
                self._after_call(generation, success=False)
            raise exc
        async with self._async_lock:
            self._after_call(generation, success=True)
        return result

    def _before_call(self) -> int:
        with self._sync_lock:
            now = _monotonic()
            state, generation = self._current_state(now)
            if state == State.OPEN:
                err = ErrCircuitOpen.with_cause(
                    RuntimeError(f"breaker {self._config.name!r} is open")
                )
                raise CircuitOpenError(err)
            if state == State.HALF_OPEN and self._counts.requests >= self._config.max_requests:
                err = ErrTooManyRequests.with_cause(
                    RuntimeError(
                        f"breaker {self._config.name!r} is half-open and at probe limit"
                    )
                )
                raise CircuitOpenError(err)
            self._counts.on_request()
            return generation

    def _after_call(self, before_generation: int, *, success: bool) -> None:
        with self._sync_lock:
            now = _monotonic()
            state, generation = self._current_state(now)
            if generation != before_generation:
                return
            if success:
                self._on_success(state, now)
            else:
                self._on_failure(state, now)

