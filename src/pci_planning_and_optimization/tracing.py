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

    def __enter__(self) -> Span:
        return self

    def __exit__(self, exc_type, exc_val, exc_tb) -> bool | None:
        if exc_val is not None:
            self.record_error(exc_val)
        self.end()
        return None


class SpanExporter(Protocol):
    def export(self, span: Span) -> None: ...
    def shutdown(self) -> None: ...


class LogExporter:

    def export(self, span: Span) -> None:
        return None

    def shutdown(self) -> None:
        return None


class NoopExporter:

    def export(self, span: Span) -> None:
        return None

    def shutdown(self) -> None:
        return None


@dataclass
class Config:
    service_name: str = "pci-planning-and-optimization"
    version: str = "1.0.0"
    enabled: bool = True
    exporter: SpanExporter | None = None


def default_config() -> Config:
    return Config(exporter=LogExporter())


class Tracer:

    __slots__ = ("_lock", "enabled", "exporter", "service_name", "version")

    def __init__(
        self,
        service_name: str,
        version: str,
        enabled: bool,
        exporter: SpanExporter | None,
    ) -> None:
        self.service_name = service_name
        self.version = version
        self.enabled = enabled
        self.exporter: SpanExporter = exporter if exporter is not None else LogExporter()
        self._lock = threading.RLock()

    def _export_span(self, span: Span) -> None:
        if not self.enabled or self.exporter is None:
            return
        try:
            self.exporter.export(span)
        except Exception as exc:
            _log.warning("[TRACING] Failed to export span: %s", exc)


_tracer_lock = threading.Lock()
_default_tracer: Tracer | None = None


def init(cfg: Config) -> None:
    global _default_tracer
    with _tracer_lock:
        if _default_tracer is not None:
            return
        _default_tracer = Tracer(
            service_name=cfg.service_name,
            version=cfg.version,
            enabled=cfg.enabled,
            exporter=cfg.exporter if cfg.exporter is not None else LogExporter(),
        )
        _log.info(
            "[TRACING] Initialized tracer for service: %s (enabled: %s)",
            cfg.service_name,
            cfg.enabled,
        )


def _get_tracer() -> Tracer:
    global _default_tracer
    if _default_tracer is None:
        init(default_config())
    assert _default_tracer is not None
    return _default_tracer


def shutdown() -> None:
    global _default_tracer
    if _default_tracer is not None and _default_tracer.exporter is not None:
        _default_tracer.exporter.shutdown()
    _default_tracer = None


current_span_var: ContextVar[Span | None] = ContextVar("current_span", default=None)


def span_from_context() -> Span | None:
    return current_span_var.get()


def trace_id_from_context() -> str:
    span = current_span_var.get()
    return span.trace_id if span is not None else ""


def span_id_from_context() -> str:
    span = current_span_var.get()
    return span.span_id if span is not None else ""


def correlation_id() -> str:
    cid = trace_id_from_context()
    return cid if cid else _generate_trace_id()


def with_correlation_id() -> Span:
    existing = current_span_var.get()
    if existing is not None and existing.trace_id:
        return existing
    span = Span(
        trace_id=_generate_trace_id(),
        span_id=_generate_span_id(),
    )
    span._ctx_token = current_span_var.set(span)
    return span


SpanOption = Any


def with_span_kind(kind: SpanKind) -> SpanOption:
    def apply(s: Span) -> None:
        s.kind = kind

    return apply


def with_attributes(*attrs: Attribute) -> SpanOption:
    def apply(s: Span) -> None:
        for a in attrs:
            s.attributes[a.key] = a.value

    return apply


def start_span(name: str, *options: SpanOption) -> Span:
    tracer = _get_tracer()
    parent = current_span_var.get()

    span = Span(
        span_id=_generate_span_id(),
        name=name,
        kind=SpanKind.INTERNAL,
    )
    if parent is not None:
        span.trace_id = parent.trace_id
        span.parent_id = parent.span_id
    else:
        span.trace_id = _generate_trace_id()

    for opt in options:
        if opt is not None:
            opt(span)

    span.attributes["service.name"] = tracer.service_name
    span.attributes["service.version"] = tracer.version

    span._ctx_token = current_span_var.set(span)
    return span


def _generate_trace_id() -> str:
    return str(uuid.uuid4())


def _generate_span_id() -> str:
    return str(uuid.uuid4())[:16]


def _truncate_id(span_or_trace_id: str) -> str:
    if not span_or_trace_id:
        return "root"
    return span_or_trace_id[:8] if len(span_or_trace_id) > 8 else span_or_trace_id


def trace_kafka_consume(topic: str, partition: int, offset: int) -> Span:
    return start_span(
        "kafka.consume",
        with_span_kind(SpanKind.CONSUMER),
        with_attributes(
            string_attr("messaging.system", "kafka"),
            string_attr("messaging.destination", topic),
            int_attr("messaging.kafka.partition", partition),
            int_attr("messaging.kafka.offset", offset),
        ),
    )


def trace_sftp_download(host: str, path: str, expected_size: int) -> Span:
    return start_span(
        "sftp.download",
        with_span_kind(SpanKind.CLIENT),
        with_attributes(
            string_attr("sftp.host", host),
            string_attr("sftp.path", path),
            int_attr("sftp.expected_size", expected_size),
        ),
    )


def trace_xml_parse(filename: str) -> Span:
    return start_span(
        "xml.parse",
        with_attributes(string_attr("file.name", filename)),
    )


def trace_influxdb_write(measurement: str, point_count: int) -> Span:
    return start_span(
        "influxdb.write",
        with_span_kind(SpanKind.CLIENT),
        with_attributes(
            string_attr("db.system", "influxdb"),
            string_attr("db.operation", "write"),
            string_attr("influxdb.measurement", measurement),
            int_attr("influxdb.point_count", point_count),
        ),
    )


def trace_alert_evaluation(gnb_id: str, rule_count: int) -> Span:
    return start_span(
        "alert.evaluate",
        with_attributes(
            string_attr("gnb_id", gnb_id),
            int_attr("rule_count", rule_count),
        ),
    )


def log_with_trace(fmt: str, *args: Any) -> None:
    trace_id = trace_id_from_context()
    span_id = span_id_from_context()
    prefix = ""
    if trace_id:
        prefix = f"[trace={trace_id[:8]} span={span_id[:8]}] "
    _log.info(prefix + fmt, *args)


__all__ = [
    "Attribute",
    "Config",
    "LogExporter",
    "NoopExporter",
    "Span",
    "SpanEvent",
    "SpanExporter",
    "SpanKind",
    "Status",
    "Tracer",
    "bool_attr",
    "correlation_id",
    "current_span_var",
    "default_config",
    "duration_attr",
    "float_attr",
    "init",
    "int_attr",
    "log_with_trace",
    "shutdown",
    "span_from_context",
    "span_id_from_context",
    "start_span",
    "string_attr",
    "time",
    "trace_alert_evaluation",
    "trace_id_from_context",
    "trace_influxdb_write",
    "trace_kafka_consume",
    "trace_sftp_download",
    "trace_xml_parse",
    "with_attributes",
    "with_correlation_id",
    "with_span_kind",
]
