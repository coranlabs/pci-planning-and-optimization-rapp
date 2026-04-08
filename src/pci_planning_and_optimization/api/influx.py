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
from dataclasses import dataclass, field
from typing import Any

from pci_planning_and_optimization.api import influx_schema as S
from pci_planning_and_optimization.app_config import InfluxConfig

_log = logging.getLogger("pci_planning_and_optimization.api.influx")


class _LogThrottle:

    def __init__(self, interval_s: float = 60.0) -> None:
        self.interval_s = interval_s
        self._last: dict[str, float] = {}
        self._lock = threading.Lock()

    def should_log(self, key: str) -> bool:
        now = time.time()
        with self._lock:
            last = self._last.get(key, 0.0)
            if now - last >= self.interval_s:
                self._last[key] = now
                return True
            return False


_throttle = _LogThrottle()


def _influx_configured(cfg: InfluxConfig, who: str) -> bool:
    if not cfg.enabled:
        return False
    if not cfg.token:
        _log.warning(
            "%s: influxdb.enabled is set but no token is configured — "
            "writes would fail on every batch, so Influx stays off. "
            "Set INFLUX_TOKEN.", who,
        )
        return False
    return True


