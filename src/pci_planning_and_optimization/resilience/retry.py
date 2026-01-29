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
import errno
import random
import threading
import time
from collections.abc import Awaitable, Callable
from dataclasses import dataclass
from typing import Final

import tenacity as _tenacity

from pci_planning_and_optimization.errors import AppError
from pci_planning_and_optimization.errors import is_retryable as _err_is_retryable
from pci_planning_and_optimization.logging_setup import Logger, with_component

__all__ = [
    "Config",
    "IsRetryableFunc",
    "Result",
    "RetryableFunc",
    "RetryableSyncFunc",
    "aggressive_config",
    "backoff",
    "default_config",
    "default_is_retryable",
    "do",
    "do_sync",
    "do_sync_with_retry_check",
    "do_with_retry_check",
    "http_config",
    "http_is_retryable",
    "is_http_status_retryable",
    "tenacity",
]

tenacity = _tenacity


@dataclass(frozen=True, slots=True)
class Config:

    max_attempts: int

    initial_interval: float

    max_interval: float

    multiplier: float

    jitter_factor: float


def default_config() -> Config:
    return Config(
        max_attempts=3,
        initial_interval=1.0,
        max_interval=30.0,
        multiplier=2.0,
        jitter_factor=0.5,
    )


def http_config() -> Config:
    return Config(
        max_attempts=3,
        initial_interval=0.5,
        max_interval=10.0,
        multiplier=2.0,
        jitter_factor=0.3,
    )


def aggressive_config() -> Config:
    return Config(
        max_attempts=5,
        initial_interval=0.1,
        max_interval=5.0,
        multiplier=1.5,
        jitter_factor=0.25,
    )


@dataclass(slots=True)
class Result:

    attempts: int = 0

    duration: float = 0.0

    last_err: BaseException | None = None


RetryableFunc = Callable[[int], Awaitable[None]]

RetryableSyncFunc = Callable[[int], None]

IsRetryableFunc = Callable[[BaseException], bool]


async def do(cfg: Config, fn: RetryableFunc) -> Result:
    return await do_with_retry_check(cfg, fn, default_is_retryable)


async def do_with_retry_check(
    cfg: Config,
    fn: RetryableFunc,
    is_retryable: IsRetryableFunc,
) -> Result:
    log = with_component("retry")
    start = time.monotonic()
    result = Result()
    interval = cfg.initial_interval

    for attempt in range(1, cfg.max_attempts + 1):
        result.attempts = attempt

        try:
            await fn(attempt)
        except asyncio.CancelledError:
            result.last_err = asyncio.CancelledError()
            result.duration = time.monotonic() - start
            raise
        except BaseException as err:
            result.last_err = err

            if not is_retryable(err):
                _log_non_retryable(log, attempt, cfg.max_attempts, err)
                break

            if attempt >= cfg.max_attempts:
                _log_exhausted(log, cfg.max_attempts, err)
                break

            delay = _calculate_backoff(interval, cfg.jitter_factor)
            _log_retrying(log, attempt, cfg.max_attempts, err, delay)

            try:
                await asyncio.sleep(delay)
            except asyncio.CancelledError:
                result.last_err = asyncio.CancelledError()
                result.duration = time.monotonic() - start
                raise

            interval = min(interval * cfg.multiplier, cfg.max_interval)
            continue
        else:
            result.last_err = None
            result.duration = time.monotonic() - start
            return result

    result.duration = time.monotonic() - start
    return result


