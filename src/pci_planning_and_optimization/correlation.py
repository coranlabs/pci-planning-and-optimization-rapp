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

from scipy.stats import mannwhitneyu

from pci_planning_and_optimization.models import Cell, Network, RelationSource, Technology

DEFAULT_MIN_PAIR_ATTEMPTS = 30

DEFAULT_MIN_POOL_SIZE = 5

DEFAULT_P_VALUE_THRESHOLD = 0.05

CLASS_COLLISION = "collision"
CLASS_CONFUSION = "confusion"
CLASS_MOD3_ONLY = "mod3_only"
CLASS_MOD4_ONLY = "mod4_only"
CLASS_MOD30_ONLY = "mod30_only"
CLASS_MULTI_MOD = "multi_mod"
CLASS_CLEAN = "clean"

VERDICT_SHIP = "SHIP"
VERDICT_DO_NOT_SHIP = "DO NOT SHIP"
VERDICT_NEEDS_MORE_DATA = "NEEDS MORE DATA"


@dataclass
class ClassStats:

    name: str
    n_pairs: int = 0
    total_attempts: int = 0
    total_failures: int = 0
    pair_failure_rates: list[float] = field(default_factory=list, repr=False)

    @property
    def weighted_failure_rate(self) -> float:
        if self.total_attempts == 0:
            return 0.0
        return self.total_failures / self.total_attempts

    @property
    def mean_pair_failure_rate(self) -> float:
        if not self.pair_failure_rates:
            return 0.0
        return sum(self.pair_failure_rates) / len(self.pair_failure_rates)

    def to_dict(self) -> dict[str, object]:
        return {
            "name": self.name,
            "n_pairs": self.n_pairs,
            "total_attempts": self.total_attempts,
            "total_failures": self.total_failures,
            "weighted_failure_rate": round(self.weighted_failure_rate, 5),
            "mean_pair_failure_rate": round(self.mean_pair_failure_rate, 5),
        }


@dataclass
class HoCorrelationReport:

    technology: str
    generated_at: str
    min_correlation_ratio: float
    min_pair_attempts: int
    min_pool_size: int
    p_value_threshold: float

    n_pairs_total: int
    n_pairs_below_attempt_threshold: int

    classes: dict[str, ClassStats]

    any_conflict_failure_rate: float
    clean_failure_rate: float
    ratio: float | None
    p_value: float | None

    gate_passed: bool
    verdict: str
    reason: str

    def to_dict(self) -> dict[str, object]:
        d = asdict(self)
        d["classes"] = {name: cs.to_dict() for name, cs in self.classes.items()}
        if d["any_conflict_failure_rate"] is not None:
            d["any_conflict_failure_rate"] = round(d["any_conflict_failure_rate"], 5)
        if d["clean_failure_rate"] is not None:
            d["clean_failure_rate"] = round(d["clean_failure_rate"], 5)
        if d["ratio"] is not None:
            d["ratio"] = round(d["ratio"], 4)
        if d["p_value"] is not None:
            d["p_value"] = round(d["p_value"], 6)
        return d


