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

from copy import copy
from dataclasses import dataclass, field
from enum import StrEnum
from http import HTTPStatus
from typing import Any, Self

from pydantic import BaseModel, ConfigDict, Field


class ErrorCategory(StrEnum):
    NETWORK = "NETWORK"
    TIMEOUT = "TIMEOUT"
    AUTHENTICATION = "AUTH"
    VALIDATION = "VALIDATION"
    NOT_FOUND = "NOT_FOUND"
    CONFLICT = "CONFLICT"
    RATE_LIMIT = "RATE_LIMIT"
    CIRCUIT_OPEN = "CIRCUIT_OPEN"
    UNAVAILABLE = "UNAVAILABLE"
    INTERNAL = "INTERNAL"
    CONFIGURATION = "CONFIG"
    PARSE = "PARSE"


class Severity(StrEnum):
    CRITICAL = "CRITICAL"
    ERROR = "ERROR"
    WARNING = "WARNING"
    INFO = "INFO"


_CATEGORY_TO_HTTP_STATUS: dict[ErrorCategory, int] = {
    ErrorCategory.NETWORK: HTTPStatus.SERVICE_UNAVAILABLE,
    ErrorCategory.TIMEOUT: HTTPStatus.SERVICE_UNAVAILABLE,
    ErrorCategory.UNAVAILABLE: HTTPStatus.SERVICE_UNAVAILABLE,
    ErrorCategory.AUTHENTICATION: HTTPStatus.UNAUTHORIZED,
    ErrorCategory.VALIDATION: HTTPStatus.BAD_REQUEST,
    ErrorCategory.NOT_FOUND: HTTPStatus.NOT_FOUND,
    ErrorCategory.CONFLICT: HTTPStatus.CONFLICT,
    ErrorCategory.RATE_LIMIT: HTTPStatus.TOO_MANY_REQUESTS,
    ErrorCategory.CIRCUIT_OPEN: HTTPStatus.SERVICE_UNAVAILABLE,
    ErrorCategory.CONFIGURATION: HTTPStatus.INTERNAL_SERVER_ERROR,
    ErrorCategory.PARSE: HTTPStatus.BAD_REQUEST,
    ErrorCategory.INTERNAL: HTTPStatus.INTERNAL_SERVER_ERROR,
}

_RETRYABLE_CATEGORIES: frozenset[ErrorCategory] = frozenset(
    {
        ErrorCategory.NETWORK,
        ErrorCategory.TIMEOUT,
        ErrorCategory.UNAVAILABLE,
        ErrorCategory.RATE_LIMIT,
    }
)


def _category_to_http_status(category: ErrorCategory) -> int:
    return _CATEGORY_TO_HTTP_STATUS.get(category, HTTPStatus.INTERNAL_SERVER_ERROR)


def _is_retryable_category(category: ErrorCategory) -> bool:
    return category in _RETRYABLE_CATEGORIES


@dataclass
class AppError(Exception):

    category: ErrorCategory
    code: str
    message: str
    severity: Severity = Severity.ERROR
    retryable: bool = False
    http_status: int = HTTPStatus.INTERNAL_SERVER_ERROR
    cause: BaseException | None = None
    context: dict[str, Any] = field(default_factory=dict)
    component: str = ""
    operation: str = ""

    def __post_init__(self) -> None:
        super().__init__(self.__str__())
        if self.cause is not None:
            self.__cause__ = self.cause

    def __reduce__(self) -> tuple[Any, tuple[Any, ...]]:
        return (
            self.__class__,
            (
                self.category,
                self.code,
                self.message,
                self.severity,
                self.retryable,
                self.http_status,
                self.cause,
                dict(self.context),
                self.component,
                self.operation,
            ),
        )

    def __str__(self) -> str:
        if self.cause is not None:
            return (
                f"[{self.category.value}] {self.code}: {self.message} "
                f"(cause: {self.cause})"
            )
        return f"[{self.category.value}] {self.code}: {self.message}"

    def matches(self, other: AppError) -> bool:
        return self.category == other.category and self.code == other.code

    def with_context(self, key: str, value: Any) -> Self:
        new = copy(self)
        new.context = {**self.context, key: value}
        return new

    def with_component(self, component: str) -> Self:
        new = copy(self)
        new.component = component
        return new

    def with_operation(self, operation: str) -> Self:
        new = copy(self)
        new.operation = operation
        return new

    def with_cause(self, cause: BaseException | None) -> Self:
        new = copy(self)
        new.cause = cause
        if cause is not None:
            new.__cause__ = cause
        return new

    def to_dict(self) -> dict[str, Any]:
        out: dict[str, Any] = {
            "category": self.category.value,
            "code": self.code,
            "message": self.message,
            "severity": self.severity.value,
            "retryable": self.retryable,
        }
        if self.http_status:
            out["http_status"] = self.http_status
        if self.context:
            out["context"] = dict(self.context)
        if self.component:
            out["component"] = self.component
        if self.operation:
            out["operation"] = self.operation
        return out

    def to_http_error(self) -> HTTPError:
        return HTTPError(
            error=self.category.value,
            code=self.code,
            message=self.message,
            details=dict(self.context) if self.context else None,
        )


class HTTPError(BaseModel):

    model_config = ConfigDict(populate_by_name=True)

    error: str = Field(alias="error")
    code: str = Field(alias="code")
    message: str = Field(alias="message")
    details: dict[str, Any] | None = Field(default=None, alias="details")


