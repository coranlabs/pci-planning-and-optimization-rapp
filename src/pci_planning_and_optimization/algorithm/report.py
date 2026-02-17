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

from dataclasses import asdict, dataclass, field
from datetime import UTC, datetime

from pci_planning_and_optimization.algorithm.conflict_graph import (
    CLASS_COLLISION,
    CLASS_CONFUSION,
    CLASS_MOD3,
    CLASS_MOD4,
    CLASS_MOD6,
    CLASS_MOD30,
    AllConflicts,
    ConflictEdge,
    all_conflicts,
)
from pci_planning_and_optimization.models import Network, Technology

DEFAULT_CONFIDENCE_WEIGHTS: dict[str, float] = {
    CLASS_COLLISION: 1.0,
    CLASS_CONFUSION: 0.7,
    CLASS_MOD3: 0.4,
    CLASS_MOD4: 0.3,
    CLASS_MOD30: 0.3,
    CLASS_MOD6: 0.2,
}


@dataclass
class ClassSummary:

    name: str
    n_pairs: int = 0
    n_real: int = 0
    n_shadow: int = 0
    total_ho_attempts: int = 0
    total_ho_failures: int = 0

    @property
    def weighted_failure_rate(self) -> float:
        return (
            self.total_ho_failures / self.total_ho_attempts
            if self.total_ho_attempts else 0.0
        )

