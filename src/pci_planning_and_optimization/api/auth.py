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

import contextvars
import functools
import hashlib
import hmac
import logging
import os
import secrets
import time
from typing import TYPE_CHECKING, Any

if TYPE_CHECKING:
    from pathlib import Path

from fastapi import APIRouter, FastAPI, Request, Response
from fastapi.responses import HTMLResponse, JSONResponse, RedirectResponse

from pci_planning_and_optimization import __version__
from pci_planning_and_optimization.resilience.ratelimit import (
    RateLimiterConfig,
    RateLimiterManager,
)

_log = logging.getLogger("pci_planning_and_optimization.api.auth")

ADMIN_USER_ENV = "RAPP_ADMIN_USERNAME"
ADMIN_PASSWORD_ENV = "RAPP_ADMIN_PASSWORD"  # noqa: S105 - the variable name, not a secret
ADMIN_HASH_ENV = "RAPP_ADMIN_PASSWORD_HASH"

SESSION_COOKIE = "pci_session"
SESSION_TTL_S = 12 * 3600

current_user: contextvars.ContextVar[str] = contextvars.ContextVar(
    "pci_current_user", default="",
)

_OPEN_PREFIXES = (
    "/login", "/api/auth/", "/static/",
    "/healthz", "/readyz", "/startupz", "/metrics",
)


def hash_password(password: str) -> str:
    salt = secrets.token_bytes(16)
    h = hashlib.scrypt(password.encode(), salt=salt, n=16384, r=8, p=1, dklen=32)
    return f"scrypt$16384$8$1${salt.hex()}${h.hex()}"


_UNKNOWN_USER_HASH = hash_password(secrets.token_urlsafe(32))


def verify_password(password: str, stored: str) -> bool:
    try:
        algo, n, r, p, salt_hex, hash_hex = stored.split("$")
        if algo != "scrypt":
            return False
        h = hashlib.scrypt(
            password.encode(), salt=bytes.fromhex(salt_hex),
            n=int(n), r=int(r), p=int(p), dklen=len(hash_hex) // 2,
        )
        return hmac.compare_digest(h.hex(), hash_hex)
    except (ValueError, TypeError):
        return False


@functools.lru_cache(maxsize=4)
def _derive(password: str) -> str:
    return hash_password(password)


def admin_credential() -> tuple[str, str]:
    username = os.environ.get(ADMIN_USER_ENV, "").strip().lower()
    stored = os.environ.get(ADMIN_HASH_ENV, "").strip()
    if not stored:
        password = os.environ.get(ADMIN_PASSWORD_ENV, "")
        if password:
            stored = _derive(password)
    if username and stored:
        return username, stored
    return "", ""


def _stored_hash(app: FastAPI, username: str) -> str:
    reader = getattr(app.state, "influx_reader", None)
    if reader is not None and reader.enabled:
        h = reader.query_auth_hash(username)
        if h:
            return str(h)
    configured, stored = admin_credential()
    return stored if configured and username == configured else ""


def _is_secure_request(request: Request) -> bool:
    forwarded = request.headers.get("x-forwarded-proto", "")
    if forwarded:
        return forwarded.split(",")[0].strip().lower() == "https"
    return request.url.scheme == "https"


