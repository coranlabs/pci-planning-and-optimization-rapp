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


def _json_default(value: Any) -> Any:
    if isinstance(value, datetime):
        return value.isoformat()
    if isinstance(value, timedelta):
        return value.total_seconds()
    if isinstance(value, BaseException):
        return str(value)
    return str(value)


def _add_timestamp(_logger: Any, _method_name: str, event_dict: EventDict) -> EventDict:
    event_dict["timestamp"] = (
        datetime.now(UTC).isoformat(timespec="microseconds").replace("+00:00", "Z")
    )
    return event_dict


def _add_level(_logger: Any, method_name: str, event_dict: EventDict) -> EventDict:
    name = method_name.upper()
    if name == "WARNING":
        name = "WARN"
    elif name == "CRITICAL":
        name = "FATAL"
    event_dict["level"] = name
    return event_dict


def _attach_trace_context(
    _logger: Any, _method_name: str, event_dict: EventDict
) -> EventDict:
    if "trace_id" not in event_dict:
        value = trace_id_var.get()
        if value:
            event_dict["trace_id"] = value
    if "span_id" not in event_dict:
        value = span_id_var.get()
        if value:
            event_dict["span_id"] = value
    return event_dict


class Logger:

    __slots__ = ("_bound", "_component", "_config", "_fields")

    def __init__(
        self,
        config: Config,
        bound: structlog.stdlib.BoundLogger | None = None,
        component: str = "",
        fields: dict[str, Any] | None = None,
    ) -> None:
        self._config = config
        self._component = component if component else config.component
        self._fields: dict[str, Any] = dict(fields) if fields else {}
        self._bound = bound if bound is not None else structlog.get_logger()

    def with_component(self, component: str) -> Self:
        return type(self)(self._config, self._bound, component, dict(self._fields))

    def with_field(self, key: str, value: Any) -> Self:
        new_fields = {**self._fields, key: value}
        return type(self)(self._config, self._bound, self._component, new_fields)

    def with_fields(self, fields: dict[str, Any]) -> Self:
        new_fields = {**self._fields, **fields}
        return type(self)(self._config, self._bound, self._component, new_fields)

    def with_error(self, err: BaseException | None) -> Self:
        if err is None:
            return self
        new_fields = {**self._fields, "error": str(err)}
        if err.__traceback__ is not None:
            new_fields["stack_trace"] = "".join(
                tb_mod.format_exception(type(err), err, err.__traceback__)
            )
        return type(self)(self._config, self._bound, self._component, new_fields)

    def with_duration(self, duration: timedelta | float) -> Self:
        if isinstance(duration, timedelta):
            ms = duration.total_seconds() * 1000.0
        else:
            ms = float(duration) * 1000.0
        return self.with_field("duration_ms", ms)

    def with_context(self, *, trace_id: str | None = None, span_id: str | None = None) -> Self:
        new_fields = dict(self._fields)
        if trace_id is not None:
            new_fields["trace_id"] = trace_id
        if span_id is not None:
            new_fields["span_id"] = span_id
        return type(self)(self._config, self._bound, self._component, new_fields)

    def _enabled(self, level: LogLevel) -> bool:
        return level.numeric >= self._config.level.numeric

    def _emit(self, level: LogLevel, msg: str) -> None:
        if not self._enabled(level):
            return
        kwargs: dict[str, Any] = dict(self._fields)
        if self._component:
            kwargs["component"] = self._component
        method = level.name.lower()
        if method == "warn":
            method = "warning"
        elif method == "fatal":
            method = "critical"
        getattr(self._bound, method)(msg, **kwargs)

    def debug(self, msg: str) -> None:
        self._emit(LogLevel.DEBUG, msg)

    def debugf(self, fmt: str, *args: Any) -> None:
        self._emit(LogLevel.DEBUG, fmt % args if args else fmt)

    def info(self, msg: str) -> None:
        self._emit(LogLevel.INFO, msg)

    def infof(self, fmt: str, *args: Any) -> None:
        self._emit(LogLevel.INFO, fmt % args if args else fmt)

    def warn(self, msg: str) -> None:
        self._emit(LogLevel.WARN, msg)

    def warnf(self, fmt: str, *args: Any) -> None:
        self._emit(LogLevel.WARN, fmt % args if args else fmt)

    def error(self, msg: str) -> None:
        self._emit(LogLevel.ERROR, msg)

    def errorf(self, fmt: str, *args: Any) -> None:
        self._emit(LogLevel.ERROR, fmt % args if args else fmt)

    def fatal(self, msg: str) -> None:
        self._emit(LogLevel.FATAL, msg)
        sys.exit(1)

    def fatalf(self, fmt: str, *args: Any) -> None:
        self._emit(LogLevel.FATAL, fmt % args if args else fmt)
        sys.exit(1)


def configure(config: Config) -> Logger:
    colours = config.console and _supports_colour(config.output)
    renderer: Processor
    if config.console:
        renderer = _console_renderer(colours)
    elif config.json_format:
        renderer = _render_log_entry
    else:
        renderer = _render_plain

    processors: list[Processor] = [
        structlog.contextvars.merge_contextvars,
        _attach_trace_context,
        _add_timestamp,
        _add_level,
    ]
    if config.include_caller:
        processors.append(
            structlog.processors.CallsiteParameterAdder(
                parameters=[
                    structlog.processors.CallsiteParameter.FILENAME,
                    structlog.processors.CallsiteParameter.LINENO,
                ]
            )
        )
        processors.append(_caller_compose)
    processors.append(renderer)

    structlog.configure(
        processors=processors,
        wrapper_class=structlog.stdlib.BoundLogger,
        context_class=dict,
        logger_factory=structlog.PrintLoggerFactory(file=config.output),
        cache_logger_on_first_use=True,
    )
    _configure_stdlib(config, renderer)
    return Logger(config)


def _supports_colour(stream: IO[str]) -> bool:
    if os.environ.get("NO_COLOR"):
        return False
    try:
        return bool(stream.isatty())
    except Exception:
        return False


def _configure_stdlib(config: Config, renderer: Processor) -> None:
    handler = stdlib_logging.StreamHandler(config.output)
    handler.setFormatter(
        structlog.stdlib.ProcessorFormatter(
            processor=renderer,
            foreign_pre_chain=[
                _attach_trace_context,
                _add_timestamp,
                _add_level,
                _component_from_record,
            ],
        )
    )
    stdlib_logging.basicConfig(
        level=config.level.numeric, handlers=[handler], force=True
    )


def _caller_compose(
    _logger: Any, _method_name: str, event_dict: EventDict
) -> EventDict:
    filename = event_dict.pop("filename", None)
    lineno = event_dict.pop("lineno", None)
    if filename and lineno is not None:
        event_dict["caller"] = f"{filename}:{lineno}"
    return event_dict


_global_logger: Logger = Logger(default_config())


def set_global(logger: Logger) -> None:
    global _global_logger
    _global_logger = logger


def get_global() -> Logger:
    return _global_logger


def debug(msg: str) -> None:
    _global_logger.debug(msg)


def debugf(fmt: str, *args: Any) -> None:
    _global_logger.debugf(fmt, *args)


def info(msg: str) -> None:
    _global_logger.info(msg)


def infof(fmt: str, *args: Any) -> None:
    _global_logger.infof(fmt, *args)


def warn(msg: str) -> None:
    _global_logger.warn(msg)


def warnf(fmt: str, *args: Any) -> None:
    _global_logger.warnf(fmt, *args)


def error(msg: str) -> None:
    _global_logger.error(msg)


def errorf(fmt: str, *args: Any) -> None:
    _global_logger.errorf(fmt, *args)


def fatal(msg: str) -> None:
    _global_logger.fatal(msg)


def fatalf(fmt: str, *args: Any) -> None:
    _global_logger.fatalf(fmt, *args)


def with_component(component: str) -> Logger:
    return _global_logger.with_component(component)


def with_field(key: str, value: Any) -> Logger:
    return _global_logger.with_field(key, value)


def with_fields(fields: dict[str, Any]) -> Logger:
    return _global_logger.with_fields(fields)


def with_error(err: BaseException | None) -> Logger:
    return _global_logger.with_error(err)


class RequestLogger:

    __slots__ = ("_logger",)

    def __init__(self, logger: Logger) -> None:
        self._logger = logger

    def log_request(
        self,
        method: str,
        path: str,
        status_code: int,
        duration: timedelta | float,
        fields: dict[str, Any] | None = None,
    ) -> None:
        entry = (
            self._logger.with_fields(fields or {})
            .with_field("method", method)
            .with_field("path", path)
            .with_field("status_code", status_code)
            .with_duration(duration)
        )
        if status_code >= 500:
            entry.error("Request failed")
        elif status_code >= 400:
            entry.warn("Request error")
        else:
            entry.info("Request completed")


LOG_FORMAT_ENV: str = "RAPP_LOG_FORMAT"


def setup_logging(level: str = "INFO", stream: IO[str] | None = None) -> Logger:
    log_level = LogLevel.from_name(level)
    fmt = os.environ.get(LOG_FORMAT_ENV, "json").strip().lower()
    logger = configure(
        Config(
            level=log_level,
            output=stream,
            console=fmt == "console",
            json_format=fmt != "plain",
        )
    )
    set_global(logger)
    return logger


def with_tech(logger: Logger | stdlib_logging.Logger | None, tech: str) -> Any:
    if isinstance(logger, stdlib_logging.Logger):
        return stdlib_logging.LoggerAdapter(logger, {"tech": tech})
    base = logger if logger is not None else get_global()
    return base.with_field("tech", tech)


__all__ = [
    "LOG_FORMAT_ENV",
    "Config",
    "LogLevel",
    "Logger",
    "RequestLogger",
    "bind_contextvars",
    "configure",
    "debug",
    "debugf",
    "default_config",
    "error",
    "errorf",
    "fatal",
    "fatalf",
    "get_contextvars",
    "get_global",
    "info",
    "infof",
    "set_global",
    "setup_logging",
    "short_component",
    "span_id_var",
    "trace_id_var",
    "warn",
    "warnf",
    "with_component",
    "with_error",
    "with_field",
    "with_fields",
    "with_tech",
]
