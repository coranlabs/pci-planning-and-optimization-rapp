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


