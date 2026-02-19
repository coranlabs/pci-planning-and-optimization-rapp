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

from dataclasses import dataclass

from pci_planning_and_optimization.models import Cell, Network
from pci_planning_and_optimization.weighting.base import WeightProvider

DEFAULT_MIN_SAMPLE_ATTEMPTS = 10


@dataclass
class HoFailureRateProvider(WeightProvider):

    network: Network
    min_sample_attempts: int = DEFAULT_MIN_SAMPLE_ATTEMPTS

    def weight(self, a: Cell, b: Cell) -> float:
        attempts = self.network.ho_attempts_pair(a.id, b.id)
        if attempts < self.min_sample_attempts:
            return 0.0
        return self.network.ho_failure_rate(a.id, b.id)
