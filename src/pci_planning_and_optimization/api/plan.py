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

import io
import logging
import threading
from typing import Any

from pci_planning_and_optimization.algorithm.coloring import run_optimization
from pci_planning_and_optimization.algorithm.conflict_graph import all_conflicts, prepare_network
from pci_planning_and_optimization.models import (
    Cell,
    NeighborRelation,
    Network,
    RelationSource,
    Technology,
)

_log = logging.getLogger(__name__)

__all__ = [
    "EXPORT_HEADERS",
    "PlanStore",
    "network_to_plan",
    "parse_plan",
    "plan_template_bytes",
    "plan_workbook_bytes",
    "sample_plans",
]

TEMPLATE_HEADERS = [
    "cell_id", "technology", "lat", "lng", "azimuth",
    "pci", "arfcn", "duplex", "cell_type", "neighbors",
]

EXPORT_HEADERS = [
    "cell_id", "technology", "lat", "lng", "azimuth",
    "pci_before", "pci", "arfcn", "duplex", "cell_type", "neighbors",
]

_WIDTHS = {"cell_id": 22, "pci": 7, "pci_before": 11, "cell_type": 10, "neighbors": 46}

_REQUIRED = ("cell_id", "technology", "lat", "lng", "pci", "neighbors")
_ALLOWED_CELL_TYPES = {"macro", "small", "das", "indoor"}

_TECHNOLOGY_ALIASES = {
    "nr": Technology.NR, "5g": Technology.NR, "5gnr": Technology.NR,
    "nr5g": Technology.NR, "5g-nr": Technology.NR, "nr-5g": Technology.NR,
    "lte": Technology.LTE, "4g": Technology.LTE, "4glte": Technology.LTE,
    "lte4g": Technology.LTE, "eutran": Technology.LTE, "e-utran": Technology.LTE,
}

_DUPLEX_ALIASES = {"fdd": "FDD", "tdd": "TDD"}

EDGE_CLASSES = ("collision", "confusion", "mod3", "mod4", "mod30")

_SEVERITY = {"collision": 0, "confusion": 1, "mod3": 2, "mod4": 3, "mod30": 4}


def plan_workbook_bytes(
    rows: list[tuple[Any, ...]], headers: list[str] | None = None,
) -> bytes:
    import openpyxl

    headers = headers or TEMPLATE_HEADERS

    wb = openpyxl.Workbook()
    ws = wb.active
    ws.title = "PCI Plan"
    ws.append(headers)
    for i, h in enumerate(headers):
        ws.column_dimensions[openpyxl.utils.get_column_letter(i + 1)].width = _WIDTHS.get(h, 11)
    bold = openpyxl.styles.Font(bold=True)
    for cell in ws[1]:
        cell.font = bold
    ws.freeze_panes = "A2"
    ws.auto_filter.ref = f"A1:{openpyxl.utils.get_column_letter(len(headers))}{len(rows) + 1}"
    for row in rows:
        ws.append(list(row))

    buf = io.BytesIO()
    wb.save(buf)
    return buf.getvalue()


def plan_template_bytes() -> bytes:
    return plan_workbook_bytes([
        ("SITE001-1", "lte", 53.3498, -6.2603, 0, 10, 1800, "FDD", "macro",
         "SITE001-2,SITE001-3,SITE002-1"),
        ("SITE001-2", "lte", 53.3498, -6.2603, 120, 11, 1800, "FDD", "macro",
         "SITE001-1,SITE001-3,SITE002-1"),
        ("SITE001-3", "lte", 53.3498, -6.2603, 240, 12, 1800, "TDD", "macro",
         "SITE001-1,SITE001-2"),
        ("SITE002-1", "lte", 53.3520, -6.2650, 0, 10, 1800, "", "macro",
         "SITE001-1,SITE001-2"),
        ("SITE003-1", "nr", 53.3540, -6.2700, 0, 700, 632628, "", "macro",
         "SITE003-2"),
        ("SITE003-2", "nr", 53.3540, -6.2700, 120, 701, 632628, "", "macro",
         "SITE003-1"),
    ])



