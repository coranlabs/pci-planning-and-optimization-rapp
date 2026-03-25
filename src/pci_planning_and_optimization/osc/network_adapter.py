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
from collections.abc import Iterable
from typing import Any

from pci_planning_and_optimization.models import (
    Cell,
    NeighborRelation,
    Network,
    RelationSource,
    Technology,
)

_log = logging.getLogger(__name__)

__all__ = ["PM_COUNTER_NAMES", "build_network_from_pm"]


PM_COUNTER_NAMES: dict[str, str] = {
    "pci": "CELL.Pci",
    "tac": "CELL.Tac",
    "arfcn_dl": "CELL.ArfcnDl",
    "arfcn_ul": "CELL.ArfcnUl",
    "bandwidth": "CELL.BandwidthDlMhz",
    "plmn_mcc": "CELL.PlmnMcc",
    "plmn_mnc": "CELL.PlmnMnc",
    "prb_util": "CELL.PrbUtilDlPct",
    "thp_dl_kbps": "CELL.ThroughputDlKbps",
    "thp_ul_kbps": "CELL.ThroughputUlKbps",
    "active_ues": "CELL.ActiveUeCount",
    "cqi": "CELL.AvgCqi",
    "sinr_db": "CELL.AvgSinrDb",
    "bler_dl": "CELL.DlBler",
    "lat": "TOPO.Latitude",
    "lon": "TOPO.Longitude",
    "site_type": "TOPO.SiteType",
    "region": "TOPO.Region",
    "neighbors": "TOPO.Neighbors",
    "band": "CELL.BandNumber",
}

