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
import threading
import time
from dataclasses import dataclass
from typing import TYPE_CHECKING

from pci_planning_and_optimization.app_config import AppConfig

if TYPE_CHECKING:
    from pci_planning_and_optimization.osc.ingest import PmStore
from pci_planning_and_optimization.models import Network

_log = logging.getLogger("pci_planning_and_optimization.api.state")


@dataclass
class NetworkSnapshot:

    network: Network | None = None
    fetched_at: float = 0.0
    wallclock_at: float = 0.0
    last_error: str | None = None
    last_error_at: float = 0.0


class NetworkCache:

    def __init__(
        self,
        config: AppConfig,
        ttl_seconds: float = 30.0,
        pm_store: PmStore | None = None,
    ) -> None:
        self.config = config
        self.ttl_seconds = ttl_seconds
        self.pm_store = pm_store
        self._snapshot = NetworkSnapshot()
        self._lock = threading.Lock()
        self.influx_writer = None


