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


def _client_ip(request: Request) -> str:
    return request.client.host if request.client else "?"


def _prune_failures(failures: dict[str, tuple[int, float]], now: float) -> None:
    for ip in [k for k, (_, reset) in failures.items() if now > reset]:
        failures.pop(ip, None)


LOGIN_RATE = RateLimiterConfig(requests_per_second=1.0, burst_size=10)


def init_auth(app: FastAPI, ui_dir: Path) -> None:
    app.state.auth_sessions = {}
    app.state.auth_failures = {}
    app.state.login_limiter = RateLimiterManager(default_config=LOGIN_RATE)

    admin_user, admin_hash = admin_credential()
    if not admin_user:
        _log.error(
            "auth: no operator account configured - set %s with %s (or %s). "
            "Every login is refused until one is set.",
            ADMIN_USER_ENV, ADMIN_PASSWORD_ENV, ADMIN_HASH_ENV,
        )
    else:
        writer = getattr(app.state, "influx_writer", None)
        if writer is not None and writer.enabled:
            writer.write_auth_user(admin_user, admin_hash)

    router = APIRouter()

    login_path = ui_dir / "login.html"
    login_html = (
        login_path.read_text(encoding="utf-8") if login_path.is_file()
        else "<!DOCTYPE html><title>Sign in</title><p>login.html is missing from the UI bundle.</p>"
    ).replace("__APP_VERSION__", f"v{__version__}")

    @router.get("/login", include_in_schema=False)
    def login_page() -> HTMLResponse:
        return HTMLResponse(login_html)

    @router.post("/api/auth/login")
    async def login(request: Request, payload: dict[str, Any]) -> Response:
        now = time.time()
        ip = _client_ip(request)
        if not app.state.login_limiter.allow(ip):
            return JSONResponse({"ok": False, "error": "Too many attempts — try again later."},
                                status_code=429)
        _prune_failures(app.state.auth_failures, now)
        count, reset = app.state.auth_failures.get(ip, (0, now + 600))
        if now > reset:
            count, reset = 0, now + 600
        if count >= 8:
            return JSONResponse({"ok": False, "error": "Too many attempts — try again later."},
                                status_code=429)

        username = str(payload.get("username", "")).strip().lower()
        password = str(payload.get("password", ""))
        stored = _stored_hash(app, username)
        verified = verify_password(password, stored or _UNKNOWN_USER_HASH)
        if not stored or not verified:
            app.state.auth_failures[ip] = (count + 1, reset)
            _log.warning("auth: failed login for %r from %s", username, ip)
            return JSONResponse({"ok": False, "error": "Invalid username or password."},
                                status_code=401)

        app.state.auth_failures.pop(ip, None)
        token = secrets.token_urlsafe(32)
        app.state.auth_sessions[token] = (username, now + SESSION_TTL_S)
        resp = JSONResponse({"ok": True})
        resp.set_cookie(
            SESSION_COOKIE, token,
            max_age=SESSION_TTL_S, httponly=True, samesite="lax",
            secure=_is_secure_request(request),
        )
        _log.info("auth: %s logged in from %s", username, ip)
        return resp

    @router.post("/api/auth/logout")
    async def logout(request: Request) -> Response:
        token = request.cookies.get(SESSION_COOKIE, "")
        app.state.auth_sessions.pop(token, None)
        resp = JSONResponse({"ok": True})
        resp.delete_cookie(SESSION_COOKIE)
        return resp

    app.include_router(router)

    @app.middleware("http")
    async def _require_session(request: Request, call_next: Any) -> Response:
        path = request.url.path
        if path.startswith(_OPEN_PREFIXES):
            open_resp: Response = await call_next(request)
            return open_resp
        token = request.cookies.get(SESSION_COOKIE, "")
        session = app.state.auth_sessions.get(token)
        if session is not None and session[1] > time.time():
            current_user.set(session[0])
            resp: Response = await call_next(request)
            return resp
        if path.startswith("/api/"):
            return JSONResponse({"ok": False, "error": "authentication required"},
                                status_code=401)
        return RedirectResponse(url="/login")
