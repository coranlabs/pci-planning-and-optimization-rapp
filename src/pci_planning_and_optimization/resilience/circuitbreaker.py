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


