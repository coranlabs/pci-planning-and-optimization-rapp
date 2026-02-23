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

from pci_planning_and_optimization.models import Cell, Network
from pci_planning_and_optimization.weighting.base import WeightProvider

_log = logging.getLogger(__name__)


@dataclass
class CellLevelHoFallback(WeightProvider):

    network: Network
    min_sample_attempts: int = 10
    _warned: bool = field(default=False, init=False, repr=False)

    def __post_init__(self) -> None:
        self._cell_attempt_total: dict[str, int] = {}

    def weight(self, a: Cell, b: Cell) -> float:
        if not self._warned:
            _log.warning(
                "CellLevelHoFallback active — per-pair HO counters absent; "
                "weights are inferred by proportional attribution from cell "
                "totals, not measured directly.",
            )
            self._warned = True

        attempts_pair = self.network.ho_attempts_pair(a.id, b.id)
        if attempts_pair < self.min_sample_attempts:
            return 0.0

        pair_failures = self._sum_pair_failures(a.id, b.id)
        if pair_failures > 0:
            return pair_failures / attempts_pair

        a_attempts_total = self._cell_attempts(a)
        b_attempts_total = self._cell_attempts(b)
        if a_attempts_total == 0 and b_attempts_total == 0:
            return 0.0

        contrib_a = (
            a.ho_attempts_total - a.ho_successes_total
        ) * (attempts_pair / a_attempts_total) if a_attempts_total else 0.0
        contrib_b = (
            b.ho_attempts_total - b.ho_successes_total
        ) * (attempts_pair / b_attempts_total) if b_attempts_total else 0.0

        inferred_failures = contrib_a + contrib_b
        if inferred_failures < 0:
            inferred_failures = 0.0
        return inferred_failures / attempts_pair

    def _cell_attempts(self, cell: Cell) -> int:
        if cell.id not in self._cell_attempt_total:
            self._cell_attempt_total[cell.id] = max(0, cell.ho_attempts_total)
        return self._cell_attempt_total[cell.id]

    def _sum_pair_failures(self, a_id: str, b_id: str) -> int:
        fwd = self.network.relation(a_id, b_id)
        rev = self.network.relation(b_id, a_id)
        return (fwd.ho_failures if fwd else 0) + (rev.ho_failures if rev else 0)
