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
import traceback
from collections.abc import Awaitable, Callable
from dataclasses import dataclass
from http import HTTPStatus
from typing import Any, TypeVar

from fastapi import Request, Response
from fastapi.responses import JSONResponse
from starlette.middleware.base import BaseHTTPMiddleware, RequestResponseEndpoint
from starlette.types import ASGIApp

from pci_planning_and_optimization.errors import (
    ERR_PANIC,
    AppError,
    to_app_error,
)
from pci_planning_and_optimization.logging_setup import Logger, get_global, with_component
from pci_planning_and_optimization.tracing import current_span_var

T = TypeVar("T")

PanicCallback = Callable[[BaseException, str], None]


@dataclass(slots=True)
class RecoveryConfig:

    enable_stack_trace: bool = True
    on_panic: PanicCallback | None = None


def default_recovery_config() -> RecoveryConfig:
    return RecoveryConfig(enable_stack_trace=True, on_panic=None)


def _format_stack(exc: BaseException) -> str:
    return "".join(traceback.format_exception(type(exc), exc, exc.__traceback__))


def _component_logger() -> Logger:
    return with_component("recovery")


def _log_panic(
    *,
    exc: BaseException,
    location: str,
    include_stack: bool,
    extra_fields: dict[str, Any] | None = None,
) -> str:
    stack = _format_stack(exc)
    log = _component_logger().with_error(exc)
    if extra_fields:
        log = log.with_fields(extra_fields)
    if include_stack:
        log = log.with_field("stack_trace", stack)
    log.error(f"[RECOVERY] PANIC recovered in {location}: {exc}")
    return stack


def _panic_response() -> JSONResponse:
    http_error = ERR_PANIC.to_http_error()
    return JSONResponse(
        status_code=HTTPStatus.INTERNAL_SERVER_ERROR,
        content=http_error.model_dump(mode="json", by_alias=True, exclude_none=True),
    )


class RecoveryMiddleware(BaseHTTPMiddleware):

    def __init__(
        self,
        app: ASGIApp,
        config: RecoveryConfig | None = None,
    ) -> None:
        super().__init__(app)
        self._config = config if config is not None else default_recovery_config()

    async def dispatch(
        self,
        request: Request,
        call_next: RequestResponseEndpoint,
    ) -> Response:
        try:
            return await call_next(request)
        except Exception as exc:
            app_err: AppError = to_app_error(exc)

            remote_addr = request.client.host if request.client else ""
            stack = _log_panic(
                exc=exc,
                location="HTTP handler",
                include_stack=self._config.enable_stack_trace,
                extra_fields={
                    "method": request.method,
                    "path": request.url.path,
                    "remote_addr": remote_addr,
                    "error_code": app_err.code,
                    "error_category": app_err.category.value,
                },
            )

            span = current_span_var.get()
            if span is not None:
                span.record_error(exc)

            if self._config.on_panic is not None:
                try:
                    self._config.on_panic(exc, stack)
                except Exception as cb_exc:
                    _component_logger().with_error(cb_exc).error(
                        "[RECOVERY] on_panic callback raised; suppressing"
                    )

            return _panic_response()


def recovery_func(fn: Callable[[], Any]) -> BaseException | None:
    try:
        fn()
    except Exception as exc:
        _log_panic(
            exc=exc,
            location="function",
            include_stack=True,
        )
        return exc
    return None


_BACKGROUND_TASKS: set[asyncio.Task[Any]] = set()


async def _safe_run(
    coro: Awaitable[Any],
    *,
    location: str,
    on_panic: PanicCallback | None = None,
) -> None:
    try:
        await coro
    except asyncio.CancelledError:
        raise
    except Exception as exc:
        stack = _log_panic(exc=exc, location=location, include_stack=True)
        if on_panic is not None:
            try:
                on_panic(exc, stack)
            except Exception as cb_exc:
                _component_logger().with_error(cb_exc).error(
                    "[RECOVERY] on_panic callback raised; suppressing"
                )


def safe_go(coro: Awaitable[Any]) -> asyncio.Task[None]:
    task: asyncio.Task[None] = asyncio.create_task(
        _safe_run(coro, location="goroutine")
    )
    _BACKGROUND_TASKS.add(task)
    task.add_done_callback(_BACKGROUND_TASKS.discard)
    return task


def safe_go_with_callback(
    coro: Awaitable[Any],
    on_panic: PanicCallback | None,
) -> asyncio.Task[None]:
    task: asyncio.Task[None] = asyncio.create_task(
        _safe_run(coro, location="goroutine", on_panic=on_panic)
    )
    _BACKGROUND_TASKS.add(task)
    task.add_done_callback(_BACKGROUND_TASKS.discard)
    return task


def safe_go_with_restart(
    name: str,
    coro_factory: Callable[[], Awaitable[Any]],
    max_restarts: int,
) -> asyncio.Task[None]:

    async def supervisor() -> None:
        restarts = 0
        while True:
            try:
                await coro_factory()
            except asyncio.CancelledError:
                raise
            except Exception as exc:
                restarts += 1
                _log_panic(
                    exc=exc,
                    location=f"goroutine '{name}'",
                    include_stack=True,
                    extra_fields={
                        "name": name,
                        "restart": restarts,
                        "max_restarts": max_restarts,
                    },
                )
                if max_restarts > 0 and restarts >= max_restarts:
                    _component_logger().with_fields(
                        {"name": name, "max_restarts": max_restarts}
                    ).error(
                        f"[RECOVERY] Goroutine '{name}' reached max restarts "
                        f"({max_restarts}), stopping"
                    )
                    return
                continue
            return

    task: asyncio.Task[None] = asyncio.create_task(supervisor())
    _BACKGROUND_TASKS.add(task)
    task.add_done_callback(_BACKGROUND_TASKS.discard)
    return task


def must(value: T, err: BaseException | None) -> T:
    if err is not None:
        raise RuntimeError(f"must: {err}") from err
    return value


def must_not_panic(fn: Callable[[], Any]) -> BaseException | None:
    try:
        result = fn()
    except Exception as exc:
        _log_panic(exc=exc, location="callable (converted to error)", include_stack=True)
        return exc
    if isinstance(result, BaseException):
        return result
    return None


_ = get_global


__all__ = [
    "PanicCallback",
    "RecoveryConfig",
    "RecoveryMiddleware",
    "default_recovery_config",
    "must",
    "must_not_panic",
    "recovery_func",
    "safe_go",
    "safe_go_with_callback",
    "safe_go_with_restart",
]
