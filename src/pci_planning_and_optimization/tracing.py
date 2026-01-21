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

import logging
import threading
import time
import uuid
from contextvars import ContextVar
from dataclasses import dataclass, field
from datetime import UTC, datetime, timedelta
from enum import IntEnum
from typing import Any, Protocol

_log = logging.getLogger(__name__)


class SpanKind(IntEnum):
    INTERNAL = 0
    SERVER = 1
    CLIENT = 2
    PRODUCER = 3
    CONSUMER = 4


class Status(IntEnum):
    UNSET = 0
    OK = 1
    ERROR = 2


@dataclass(slots=True, frozen=True)
class Attribute:

    key: str
    value: Any


def string_attr(key: str, value: str) -> Attribute:
    return Attribute(key, value)


def int_attr(key: str, value: int) -> Attribute:
    return Attribute(key, int(value))


def float_attr(key: str, value: float) -> Attribute:
    return Attribute(key, float(value))


def bool_attr(key: str, value: bool) -> Attribute:
    return Attribute(key, bool(value))


def duration_attr(key: str, value: timedelta | float) -> Attribute:
    if isinstance(value, timedelta):
        ms = int(value.total_seconds() * 1000)
    else:
        ms = int(value * 1000)
    return Attribute(key, ms)


@dataclass(slots=True)
class SpanEvent:
    name: str
    timestamp: datetime = field(default_factory=lambda: datetime.now(UTC))
    attributes: dict[str, Any] = field(default_factory=dict)


class Span:

    __slots__ = (
        "_ctx_token",
        "_lock",
        "attributes",
        "end_time",
        "events",
        "kind",
        "name",
        "parent_id",
        "span_id",
        "start_time",
        "status",
        "status_msg",
        "trace_id",
    )

    def __init__(
        self,
        *,
        trace_id: str = "",
        span_id: str = "",
        parent_id: str = "",
        name: str = "",
        kind: SpanKind = SpanKind.INTERNAL,
    ) -> None:
        self.trace_id = trace_id
        self.span_id = span_id
        self.parent_id = parent_id
        self.name = name
        self.kind = kind
        self.start_time: datetime = datetime.now(UTC)
        self.end_time: datetime | None = None
        self.status: Status = Status.UNSET
        self.status_msg: str = ""
        self.attributes: dict[str, Any] = {}
        self.events: list[SpanEvent] = []
        self._lock = threading.Lock()
        self._ctx_token: Any = None

    def set_attributes(self, *attrs: Attribute) -> None:
        with self._lock:
            for a in attrs:
                self.attributes[a.key] = a.value

    def set_status(self, status: Status, message: str = "") -> None:
        with self._lock:
            self.status = status
            self.status_msg = message

    def record_error(self, err: BaseException | None) -> None:
        if err is None:
            return
        with self._lock:
            self.status = Status.ERROR
            self.status_msg = str(err)
            self.events.append(
                SpanEvent(
                    name="exception",
                    attributes={"exception.message": str(err)},
                )
            )

    def add_event(self, name: str, *attrs: Attribute) -> None:
        with self._lock:
            event = SpanEvent(name=name)
            for a in attrs:
                event.attributes[a.key] = a.value
            self.events.append(event)

    def end(self) -> None:
        with self._lock:
            if self.end_time is not None:
                return
            self.end_time = datetime.now(UTC)
            duration = self.end_time - self.start_time
            token, self._ctx_token = self._ctx_token, None
        if token is not None:
            try:
                current_span_var.reset(token)
            except ValueError:
                current_span_var.set(None)
        trace_prefix = self.trace_id[:8] if self.trace_id else "????????"
        span_prefix = self.span_id[:8] if self.span_id else "????????"
        parent_str = _truncate_id(self.parent_id)
        if self.status == Status.ERROR:
            _log.debug(
                "[TRACE] %s | span=%s | parent=%s | %s | %s | ERROR: %s",
                trace_prefix,
                span_prefix,
                parent_str,
                self.name,
                duration,
                self.status_msg,
            )
        else:
            _log.debug(
                "[TRACE] %s | span=%s | parent=%s | %s | %s",
                trace_prefix,
                span_prefix,
                parent_str,
                self.name,
                duration,
            )
        _get_tracer()._export_span(self)

