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

import json
import logging as stdlib_logging
import os
import sys
import traceback as tb_mod
from contextvars import ContextVar
from datetime import UTC, datetime, timedelta
from enum import StrEnum
from typing import IO, Any, Self

import structlog
from structlog.contextvars import bind_contextvars, get_contextvars
from structlog.types import EventDict, Processor


class LogLevel(StrEnum):
    DEBUG = "DEBUG"
    INFO = "INFO"
    WARN = "WARN"
    ERROR = "ERROR"
    FATAL = "FATAL"

    @property
    def numeric(self) -> int:
        return _LEVEL_TO_NUMERIC[self]

    @classmethod
    def from_name(cls, name: str) -> LogLevel:
        normalised = name.strip().upper()
        if normalised == "WARNING":
            normalised = "WARN"
        try:
            return cls(normalised)
        except ValueError:
            return cls.INFO


_LEVEL_TO_NUMERIC: dict[LogLevel, int] = {
    LogLevel.DEBUG: stdlib_logging.DEBUG,
    LogLevel.INFO: stdlib_logging.INFO,
    LogLevel.WARN: stdlib_logging.WARNING,
    LogLevel.ERROR: stdlib_logging.ERROR,
    LogLevel.FATAL: stdlib_logging.CRITICAL,
}


trace_id_var: ContextVar[str | None] = ContextVar("trace_id", default=None)
span_id_var: ContextVar[str | None] = ContextVar("span_id", default=None)


class Config:

    __slots__ = (
        "component",
        "console",
        "include_caller",
        "json_format",
        "level",
        "output",
    )

    def __init__(
        self,
        level: LogLevel = LogLevel.INFO,
        output: IO[str] | None = None,
        *,
        json_format: bool = True,
        console: bool = False,
        include_caller: bool = False,
        component: str = "",
    ) -> None:
        self.level = level
        self.output = output if output is not None else sys.stdout
        self.json_format = json_format
        self.console = console
        self.include_caller = include_caller
        self.component = component


def default_config() -> Config:
    return Config()


_TOP_LEVEL_KEYS = frozenset(
    {
        "timestamp",
        "level",
        "message",
        "component",
        "trace_id",
        "span_id",
        "caller",
        "error",
        "stack_trace",
        "duration_ms",
    }
)


def _render_log_entry(
    _logger: Any, _method_name: str, event_dict: EventDict
) -> str:
    message = event_dict.pop("event", "")

    entry: dict[str, Any] = {
        "timestamp": event_dict.pop("timestamp"),
        "level": event_dict.pop("level"),
        "message": message,
    }

    for key in ("component", "trace_id", "span_id", "caller", "error", "stack_trace"):
        value = event_dict.pop(key, None)
        if value:
            entry[key] = value

    duration_ms = event_dict.pop("duration_ms", None)
    if duration_ms:
        entry["duration_ms"] = duration_ms

    fields = {k: v for k, v in event_dict.items() if not k.startswith("_")}
    if fields:
        entry["fields"] = fields

    return json.dumps(entry, default=_json_default, separators=(",", ":"))


def _render_plain(
    _logger: Any, _method_name: str, event_dict: EventDict
) -> str:
    ts = event_dict.get("timestamp", "")
    level = event_dict.get("level", "")
    component = event_dict.get("component", "")
    message = event_dict.get("event", "")
    return f"{ts} [{level}] {component}: {message}"


_LEVEL_STYLE: dict[str, str] = {
    "DEBUG": "\x1b[90m",
    "INFO": "\x1b[36m",
    "WARN": "\x1b[33m",
    "ERROR": "\x1b[31m",
    "FATAL": "\x1b[35m",
}
_DIM = "\x1b[2m"
_CYAN = "\x1b[36m"
_RESET = "\x1b[0m"

_COMPONENT_WIDTH = 14

_COMPONENT_ALIASES: dict[str, str] = {
    "uvicorn": "http",
    "fastapi": "http",
    "starlette": "http",
    "confluent_kafka": "kafka",
    "influxdb_client": "influxdb",
}


def short_component(logger_name: str) -> str:
    parts = [p for p in logger_name.split(".") if p]
    if parts and parts[0] == "pci_planning_and_optimization":
        parts = parts[1:]
    head = parts[0] if parts else "rapp"
    return _COMPONENT_ALIASES.get(head, head)[:_COMPONENT_WIDTH]


def _component_from_record(
    _logger: Any, _method_name: str, event_dict: EventDict
) -> EventDict:
    record = event_dict.get("_record")
    if record is not None and not event_dict.get("component"):
        event_dict["component"] = short_component(record.name)
    return event_dict


def _console_renderer(colours: bool) -> Processor:

    def render(_logger: Any, _method_name: str, event_dict: EventDict) -> str:
        ts = str(event_dict.pop("timestamp", ""))[11:23]
        level = str(event_dict.pop("level", "INFO"))
        component = str(event_dict.pop("component", "") or "-")[:_COMPONENT_WIDTH]
        message = str(event_dict.pop("event", ""))

        error = event_dict.pop("error", None)
        stack = event_dict.pop("stack_trace", None)
        duration_ms = event_dict.pop("duration_ms", None)
        fields = {
            k: v for k, v in event_dict.items()
            if not k.startswith("_") and k not in ("trace_id", "span_id")
        }
        if duration_ms:
            fields["ms"] = f"{float(duration_ms):.1f}"
        if error:
            fields["error"] = error
        tail = "  ".join(f"{k}={v}" for k, v in fields.items())

        if colours:
            style = _LEVEL_STYLE.get(level, "")
            head = (
                f" {_DIM}{ts}{_RESET}  {style}{level:<5}{_RESET} {_DIM}│{_RESET} "
                f"{_DIM}{_CYAN}{component:<{_COMPONENT_WIDTH}}{_RESET}"
            )
            if tail:
                tail = f"{_DIM}{tail}{_RESET}"
        else:
            head = f" {ts}  {level:<5} │ {component:<{_COMPONENT_WIDTH}}"

        line = f"{head}{message}"
        if tail:
            line = f"{line}  {tail}"
        if stack:
            indent = "\n      "
            line += indent + indent.join(str(stack).rstrip().splitlines())
        return line

    return render


