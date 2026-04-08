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


    def get(self, *, force_refresh: bool = False) -> NetworkSnapshot:
        snap = self._snapshot
        age = time.monotonic() - snap.fetched_at if snap.fetched_at else float("inf")
        cold_start = snap.network is None
        stale = age >= self.ttl_seconds

        if not (force_refresh or cold_start or stale):
            return snap

        if force_refresh or cold_start:
            return self._do_refresh_blocking()

        if self._lock.acquire(blocking=False):
            def _bg() -> None:
                try:
                    self._refresh_under_lock()
                finally:
                    self._lock.release()
            threading.Thread(
                target=_bg, name="network-cache-refresh", daemon=True,
            ).start()
        return snap

    def _do_refresh_blocking(self) -> NetworkSnapshot:
        self._lock.acquire()
        try:
            return self._refresh_under_lock()
        finally:
            self._lock.release()

    def _refresh_under_lock(self) -> NetworkSnapshot:
        snap = self._snapshot
        age = time.monotonic() - snap.fetched_at if snap.fetched_at else float("inf")
        if snap.network is not None and age < self.ttl_seconds:
            return snap

        new_network, error = self._fetch()
        now_mono = time.monotonic()
        now_wall = time.time()
        if new_network is not None:
            self._snapshot = NetworkSnapshot(
                network=new_network,
                fetched_at=now_mono,
                wallclock_at=now_wall,
                last_error=None,
                last_error_at=0.0,
            )
        else:
            self._snapshot = NetworkSnapshot(
                network=snap.network,
                fetched_at=snap.fetched_at,
                wallclock_at=snap.wallclock_at,
                last_error=error,
                last_error_at=now_wall,
            )
        result = self._snapshot

        if new_network is not None and self.influx_writer is not None:
            def _record() -> None:
                try:
                    self.influx_writer.record_network(new_network)
                except Exception as e:
                    _log.debug("influx record_network swallowed: %s", e)
            threading.Thread(
                target=_record, name="influx-record-network", daemon=True,
            ).start()
        return result

    def is_stale(self, snap: NetworkSnapshot | None = None) -> bool:
        snap = snap or self._snapshot
        if snap.network is None:
            return True
        if snap.last_error is not None:
            return True
        age = time.monotonic() - snap.fetched_at
        return age >= self.ttl_seconds


    def _fetch(self) -> tuple[Network | None, str | None]:
        osc_cfg = self.config.osc

        try:
            if osc_cfg.pm_directory:
                from pci_planning_and_optimization.osc.ingest import load_network_from_directory

                network = load_network_from_directory(
                    osc_cfg.pm_directory,
                    max_files=osc_cfg.max_files_per_refresh,
                )
                _log.info(
                    "OSC directory ingest ok: %d cells, %d relations",
                    len(network.cells), len(network.relations),
                )
                return network, None

            if self.pm_store is None or len(self.pm_store) == 0:
                return None, (
                    "No PM data yet: waiting for VES notifyFileReady events on "
                    f"{osc_cfg.kafka.topic}. Set osc.pm_directory (or "
                    "PM_DIRECTORY) to read PM files from disk instead."
                )

            network = self.pm_store.to_network()
            _log.info(
                "OSC Kafka ingest ok: %d cells, %d relations (%d nodes buffered)",
                len(network.cells), len(network.relations), len(self.pm_store),
            )
            return network, None
        except Exception as e:
            err = f"{type(e).__name__}: {e}"
            _log.warning("OSC ingest failed: %s", err)
            return None, err
