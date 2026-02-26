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
from dataclasses import dataclass, field

from pci_planning_and_optimization.app_config import AppConfig, TechPools
from pci_planning_and_optimization.models import Cell, Network, Technology

_log = logging.getLogger(__name__)


@dataclass
class PoolSizeIssue:

    technology: str
    cell_type: str
    pool_size: int
    cell_count: int
    severity: str
    message: str

    def to_dict(self) -> dict[str, object]:
        return {
            "technology": self.technology,
            "cell_type": self.cell_type,
            "pool_size": self.pool_size,
            "cell_count": self.cell_count,
            "severity": self.severity,
            "message": self.message,
        }


@dataclass
class PoolValidationReport:

    issues: list[PoolSizeIssue] = field(default_factory=list)

    @property
    def has_errors(self) -> bool:
        return any(i.severity == "ERROR" for i in self.issues)

    def to_dict(self) -> dict[str, object]:
        return {
            "issues": [i.to_dict() for i in self.issues],
            "has_errors": self.has_errors,
        }


class OperatorPolicy:

    def __init__(self, config: AppConfig) -> None:
        self._cfg = config


    def allowed_pool_for(self, cell: Cell) -> set[int]:
        pool = self._tech_pools(cell.technology)
        cell_pool = self._range_for_type(pool, cell.cell_type)
        if not cell_pool:
            return set()
        reserved = self._range_for_type(pool, "reserved")
        return cell_pool - reserved


    def validate_pool_sizes(self, network: Network) -> PoolValidationReport:
        report = PoolValidationReport()

        bucket: dict[tuple, list[Cell]] = {}
        for c in network.cells.values():
            bucket.setdefault((c.technology, c.cell_type), []).append(c)

        for (tech, cell_type), cells in bucket.items():
            pool_size = len(self._allowed_pool_for_type(tech, cell_type))
            cell_count = len(cells)

            if pool_size == 0:
                issue = PoolSizeIssue(
                    technology=tech.value,
                    cell_type=cell_type,
                    pool_size=0,
                    cell_count=cell_count,
                    severity="ERROR",
                    message=(
                        f"No PCI pool configured for {tech.value}/{cell_type} "
                        f"(found {cell_count} cells). The optimizer will skip "
                        "every such cell."
                    ),
                )
                report.issues.append(issue)
                _log.error(issue.message)
                continue

            if pool_size < cell_count:
                issue = PoolSizeIssue(
                    technology=tech.value,
                    cell_type=cell_type,
                    pool_size=pool_size,
                    cell_count=cell_count,
                    severity="ERROR",
                    message=(
                        f"{tech.value}/{cell_type}: pool size {pool_size} < "
                        f"cell count {cell_count}. The optimizer cannot assign "
                        "a unique PCI to every cell of this type."
                    ),
                )
                report.issues.append(issue)
                _log.error(issue.message)
                continue

            if pool_size < 2 * cell_count:
                issue = PoolSizeIssue(
                    technology=tech.value,
                    cell_type=cell_type,
                    pool_size=pool_size,
                    cell_count=cell_count,
                    severity="WARN",
                    message=(
                        f"{tech.value}/{cell_type}: pool size {pool_size} "
                        f"is < 2 × cell count {cell_count}. Most PCIs will "
                        "be reused; collisions/confusions may be unavoidable."
                    ),
                )
                report.issues.append(issue)
                _log.warning(issue.message)

        return report


    def _tech_pools(self, tech: Technology) -> TechPools:
        return self._cfg.pools.lte if tech == Technology.LTE else self._cfg.pools.nr

    def _allowed_pool_for_type(self, tech: Technology, cell_type: str) -> set[int]:
        pool = self._tech_pools(tech)
        cell_pool = self._range_for_type(pool, cell_type)
        if not cell_pool:
            return set()
        reserved = self._range_for_type(pool, "reserved")
        return cell_pool - reserved

    @staticmethod
    def _range_for_type(pool: TechPools, cell_type: str) -> set[int]:
        rng = getattr(pool, cell_type, None)
        if rng is None or len(rng) != 2:
            return set()
        start, end = rng
        return set(range(start, end))
