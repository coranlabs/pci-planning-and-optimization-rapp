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


def do_sync(
    cfg: Config,
    fn: RetryableSyncFunc,
    *,
    cancel: threading.Event | None = None,
) -> Result:
    return do_sync_with_retry_check(cfg, fn, default_is_retryable, cancel=cancel)


def do_sync_with_retry_check(
    cfg: Config,
    fn: RetryableSyncFunc,
    is_retryable: IsRetryableFunc,
    *,
    cancel: threading.Event | None = None,
) -> Result:
    log = with_component("retry")
    start = time.monotonic()
    result = Result()
    interval = cfg.initial_interval

    for attempt in range(1, cfg.max_attempts + 1):
        result.attempts = attempt

        if cancel is not None and cancel.is_set():
            result.last_err = asyncio.CancelledError()
            break

        try:
            fn(attempt)
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

            if cancel is not None and cancel.wait(timeout=delay):
                result.last_err = asyncio.CancelledError()
                break
            if cancel is None:
                time.sleep(delay)

            interval = min(interval * cfg.multiplier, cfg.max_interval)
            continue
        else:
            result.last_err = None
            result.duration = time.monotonic() - start
            return result

    result.duration = time.monotonic() - start
    return result


def _calculate_backoff(base_interval: float, jitter_factor: float) -> float:
    if jitter_factor <= 0:
        return base_interval
    jitter = (random.random() * 2 - 1) * jitter_factor
    return base_interval * (1 + jitter)


def backoff(attempt: int, cfg: Config) -> float:
    if attempt <= 1:
        return _calculate_backoff(cfg.initial_interval, cfg.jitter_factor)

    interval = cfg.initial_interval
    for _ in range(1, attempt):
        interval = interval * cfg.multiplier
        if interval > cfg.max_interval:
            interval = cfg.max_interval
            break

    return _calculate_backoff(interval, cfg.jitter_factor)


_RETRYABLE_PATTERNS: Final[tuple[str, ...]] = (
    "connection refused",
    "connection reset",
    "timeout",
    "temporary",
    "unavailable",
    "too many requests",
    "service unavailable",
    "bad gateway",
    "gateway timeout",
    "i/o timeout",
    "no such host",
    "network is unreachable",
)

_HTTP_RETRYABLE_PATTERNS: Final[tuple[str, ...]] = (
    "500",
    "502",
    "503",
    "504",
    "internal server error",
    "bad gateway",
    "service unavailable",
    "gateway timeout",
)

_RETRYABLE_HTTP_STATUSES: Final[frozenset[int]] = frozenset(
    {
        408,
        429,
        500,
        502,
        503,
        504,
    }
)

_RETRYABLE_ERRNOS: Final[frozenset[int]] = frozenset(
    {errno.ECONNREFUSED, errno.ECONNRESET, errno.ETIMEDOUT}
)


def default_is_retryable(err: BaseException | None) -> bool:
    if err is None:
        return False

    if isinstance(err, asyncio.CancelledError):
        return False

    if isinstance(err, AppError):
        return err.retryable
    if _err_is_retryable(err):
        return True

    if isinstance(err, OSError) and err.errno in _RETRYABLE_ERRNOS:
        return True

    msg = str(err).lower()
    return any(pattern in msg for pattern in _RETRYABLE_PATTERNS)


def http_is_retryable(err: BaseException | None) -> bool:
    if err is None:
        return False
    if default_is_retryable(err):
        return True
    msg = str(err).lower()
    return any(pattern in msg for pattern in _HTTP_RETRYABLE_PATTERNS)


def is_http_status_retryable(status_code: int) -> bool:
    return status_code in _RETRYABLE_HTTP_STATUSES


def _log_retrying(
    log: Logger, attempt: int, max_attempts: int, err: BaseException, delay: float
) -> None:
    log.with_fields(
        {
            "attempt": attempt,
            "max_attempts": max_attempts,
            "next_delay_seconds": delay,
        }
    ).with_error(err).warn(f"Attempt {attempt}/{max_attempts} failed, retrying")


def _log_non_retryable(
    log: Logger, attempt: int, max_attempts: int, err: BaseException
) -> None:
    log.with_fields(
        {"attempt": attempt, "max_attempts": max_attempts}
    ).with_error(err).warn(
        f"Non-retryable error on attempt {attempt}/{max_attempts}"
    )


def _log_exhausted(log: Logger, max_attempts: int, err: BaseException) -> None:
    log.with_fields({"max_attempts": max_attempts}).with_error(err).warn(
        f"Max attempts reached ({max_attempts}), giving up"
    )
