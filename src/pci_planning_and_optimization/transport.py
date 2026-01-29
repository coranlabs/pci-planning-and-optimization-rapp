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
import ssl
import urllib.error
import urllib.request
from collections.abc import Mapping
from dataclasses import dataclass, field
from typing import Any, Protocol

DEFAULT_TIMEOUT_SECONDS = 30.0


class HttpTransportError(RuntimeError):
    pass


@dataclass
class HttpResponse:

    status: int
    headers: dict[str, str]
    body: bytes

    def text(self) -> str:
        return self.body.decode("utf-8", errors="replace")

    def json(self) -> Any:
        if not self.body:
            return None
        return json.loads(self.body.decode("utf-8"))


class HttpTransport(Protocol):

    def request(
        self,
        method: str,
        url: str,
        *,
        headers: Mapping[str, str] | None = None,
        body: bytes | None = None,
        timeout: float | None = None,
    ) -> HttpResponse:
        ...


@dataclass
class UrlLibTransport:

    timeout: float = DEFAULT_TIMEOUT_SECONDS
    ca_cert_path: str | None = None
    client_cert_path: str | None = None
    client_key_path: str | None = None
    _ssl_context: ssl.SSLContext = field(init=False, repr=False)

    def __post_init__(self) -> None:
        if (self.client_cert_path is None) != (self.client_key_path is None):
            raise ValueError(
                "client_cert_path and client_key_path must be set together"
            )
        if self.ca_cert_path:
            ctx = ssl.create_default_context(cafile=self.ca_cert_path)
        else:
            ctx = ssl.create_default_context()
        if self.client_cert_path and self.client_key_path:
            ctx.load_cert_chain(self.client_cert_path, self.client_key_path)
        ctx.minimum_version = ssl.TLSVersion.TLSv1_2
        self._ssl_context = ctx

    def request(
        self,
        method: str,
        url: str,
        *,
        headers: Mapping[str, str] | None = None,
        body: bytes | None = None,
        timeout: float | None = None,
    ) -> HttpResponse:
        req = urllib.request.Request(url=url, data=body, method=method.upper())
        if headers:
            for k, v in headers.items():
                req.add_header(k, v)

        effective_timeout = self.timeout if timeout is None else timeout
        try:
            with urllib.request.urlopen(
                req,
                timeout=effective_timeout,
                context=self._ssl_context,
            ) as resp:
                resp_body = resp.read()
                resp_status = resp.status
                resp_headers = self._normalise_headers(resp.headers.items())
        except urllib.error.HTTPError as e:
            resp_body = e.read() if hasattr(e, "read") else b""
            resp_status = e.code
            resp_headers = self._normalise_headers(
                e.headers.items() if e.headers else []
            )
        except urllib.error.URLError as e:
            raise HttpTransportError(f"transport error for {method} {url}: {e}") from e
        except (TimeoutError, ssl.SSLError) as e:
            raise HttpTransportError(f"transport error for {method} {url}: {e}") from e

        return HttpResponse(
            status=resp_status, headers=resp_headers, body=resp_body
        )

