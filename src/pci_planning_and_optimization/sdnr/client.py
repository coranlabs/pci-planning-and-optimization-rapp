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

import base64
import json
import logging
import urllib.parse
from dataclasses import dataclass, field

from pci_planning_and_optimization.transport import (
    HttpTransport,
    HttpTransportError,
    ResilientTransport,
    UrlLibTransport,
)

_log = logging.getLogger(__name__)


NS_MANAGED_ELEMENT = "_3gpp-common-managed-element"
NS_NR_CELL_DU = "_3gpp-nr-nrm-nrcelldu"
NS_EUTRAN_CELL_FDD = "_3gpp-eutran-nrm-eutrancellfdd"
NS_EUTRAN_CELL_TDD = "_3gpp-eutran-nrm-eutrancelltdd"
NS_GNBDU_FUNCTION = "_3gpp-nr-nrm-gnbdufunction"
NS_ENB_FUNCTION = "_3gpp-eutran-nrm-enbfunction"

DEFAULT_TIMEOUT_S = 30.0


@dataclass
class SdnrResult:

    ok: bool
    status: int
    note: str
    body: bytes | None = None


@dataclass
class SdnrClient:

    base_url: str
    username: str
    password: str
    netconf_node_id: str
    function_id: str = "1"
    transport: HttpTransport | None = None
    timeout_s: float = DEFAULT_TIMEOUT_S

    _auth_header: str = field(default="", init=False, repr=False)

    def __post_init__(self) -> None:
        if not self.base_url:
            raise ValueError("base_url is required")
        if not self.netconf_node_id:
            raise ValueError("netconf_node_id is required")
        self.base_url = self.base_url.rstrip("/")
        if self.transport is None:
            self.transport = ResilientTransport(
                inner=UrlLibTransport(timeout=self.timeout_s),
                breaker_name=f"sdnr:{self.netconf_node_id}",
            )
        creds = base64.b64encode(
            f"{self.username}:{self.password}".encode()
        ).decode("ascii")
        self._auth_header = f"Basic {creds}"


    def test_connection(self) -> SdnrResult:
        return self._do("GET", "/rests/operations", body=None)

    def check_mount_status(self) -> SdnrResult:
        path = (
            "/rests/data/network-topology:network-topology"
            "/topology=topology-netconf"
            f"/node={urllib.parse.quote(self.netconf_node_id, safe='')}"
            "?content=nonconfig"
        )
        raw = self._do("GET", path, body=None)
        if raw.status in (404, 409):
            return SdnrResult(
                ok=False, status=raw.status,
                note=(f"no NETCONF mount named {self.netconf_node_id!r} is "
                      f"registered in SDNR"),
                body=raw.body,
            )
        if not raw.ok or not raw.body:
            return raw
        try:
            payload = json.loads(raw.body.decode("utf-8"))
            nodes = payload.get("network-topology:node", [])
            status = nodes[0].get("netconf-node-topology:connection-status")
        except (UnicodeDecodeError, json.JSONDecodeError, IndexError, AttributeError) as e:
            return SdnrResult(
                ok=False, status=raw.status,
                note=f"unparseable mount-status body: {e}", body=raw.body,
            )
        if status == "connected":
            return SdnrResult(ok=True, status=raw.status, note="connected", body=raw.body)
        return SdnrResult(
            ok=False, status=raw.status,
            note=f"mount not connected (status={status!r})", body=raw.body,
        )

    def update_nr_pci(self, cell_urn: str, new_pci: int) -> SdnrResult:
        if not (0 <= new_pci <= 1007):
            return SdnrResult(
                ok=False, status=0,
                note=f"NR PCI {new_pci} out of range 0..1007",
            )
        short = _short_id(cell_urn)
        me = _managed_element(cell_urn, default=short)
        path = self._build_cell_path(
            me_name=me, cell_ns=NS_NR_CELL_DU, cell_list="NRCellDU",
            cell_short=short, leaf="attributes", func_urn=cell_urn,
        )
        body = json.dumps(
            {f"{NS_NR_CELL_DU}:attributes": {"nRPCI": int(new_pci)}}
        ).encode("utf-8")
        return self._do("PATCH", path, body=body)

