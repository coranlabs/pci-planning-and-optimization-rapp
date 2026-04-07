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

from pci_planning_and_optimization.app_config import AppConfig
from pci_planning_and_optimization.sdnr.client import SdnrClient

_log = logging.getLogger(__name__)


def make_sdnr_client(cfg: AppConfig) -> SdnrClient | None:
    s = cfg.sdnr
    if not s.enabled:
        return None
    if not s.base_url or not s.netconf_node_id:
        return None
    return SdnrClient(
        base_url=s.base_url,
        function_id=s.function_id,
        username=s.username,
        password=s.password,
        netconf_node_id=s.netconf_node_id,
        timeout_s=s.timeout_s,
    )


def preflight(client: SdnrClient) -> tuple[bool, str]:
    r = client.test_connection()
    if not r.ok:
        return False, f"connectivity probe failed: {r.note}"
    r = client.check_mount_status()
    if not r.ok:
        return False, r.note
    return True, "ok"


def apply_change(change: dict, client: SdnrClient) -> tuple[bool, str]:
    cell_urn = change.get("cell_id") or ""
    if not cell_urn:
        return False, "missing cell_id"
    tech = (change.get("technology") or "").lower()

    if tech == "nr":
        try:
            new_pci = int(change["pci_new"])
        except (KeyError, ValueError, TypeError):
            return False, "missing or non-integer pci_new"
        result = client.update_nr_pci(cell_urn, new_pci)
        return result.ok, result.note

    if tech == "lte":
        comps = change.get("pci_components_new") or {}
        try:
            group = int(comps["group"])
            sub = int(comps["sub"])
        except (KeyError, ValueError, TypeError):
            return False, "missing or non-integer pci_components_new (need group + sub)"
        result = client.update_lte_pci(
            cell_urn, group=group, sub=sub,
            mo_class=change.get("mo_class") or "EUtranCellFDD",
        )
        return result.ok, result.note

    return False, f"unknown or missing technology: {tech!r}"
