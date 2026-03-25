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
import time
from pathlib import Path
from typing import Any

from pci_planning_and_optimization.app_config import AppConfig
from pci_planning_and_optimization.models import Network
from pci_planning_and_optimization.osc.network_adapter import build_network_from_pm

_log = logging.getLogger(__name__)

__all__ = ["PmStore", "build_sftp_client", "load_network_from_directory"]


DEFAULT_RETENTION_S = 86400.0


class PmStore:

    def __init__(self, retention_s: float = DEFAULT_RETENTION_S) -> None:
        self._by_node: dict[str, tuple[Any, float]] = {}
        self.retention_s = retention_s
        self.last_ingest_at: float = 0.0

    def add(self, pm_data: Any) -> None:
        node = getattr(pm_data, "source_name", "") or ""
        if not node:
            return
        now = time.time()
        self._by_node[node] = (pm_data, now)
        self.last_ingest_at = now
        self._prune(now)

    def _prune(self, now: float) -> None:
        cutoff = now - self.retention_s
        for node in [n for n, (_, at) in self._by_node.items() if at < cutoff]:
            del self._by_node[node]

    @property
    def age_seconds(self) -> float | None:
        if not self.last_ingest_at:
            return None
        return max(0.0, time.time() - self.last_ingest_at)

    def __len__(self) -> int:
        cutoff = time.time() - self.retention_s
        return sum(1 for _, at in self._by_node.values() if at >= cutoff)

    def to_network(self) -> Network:
        self._prune(time.time())
        return build_network_from_pm([d for d, _ in self._by_node.values()])


def load_network_from_directory(
    directory: str | Path,
    *,
    max_files: int = 5000,
) -> Network:
    from pci_planning_and_optimization.sftp.xml_parser import XMLParser

    root = Path(directory)
    if not root.is_dir():
        raise FileNotFoundError(f"PM directory not found: {root}")

    files = sorted(root.glob("*.xml"))
    if max_files and len(files) > max_files:
        _log.info(
            "PM directory has %d files; using the newest %d",
            len(files), max_files,
        )
        files = files[-max_files:]

    parser = XMLParser()
    store = PmStore()
    skipped = 0
    for path in files:
        try:
            store.add(parser.parse(path.read_bytes(), str(path)))
        except Exception as exc:
            skipped += 1
            _log.debug("skipping %s: %s", path.name, exc)

    _log.info(
        "PM directory %s: %d files, %d nodes, %d skipped",
        root, len(files), len(store), skipped,
    )
    return store.to_network()


def build_sftp_client(config: AppConfig) -> Any | None:
    sftp_cfg = config.osc.sftp
    if not sftp_cfg.enabled:
        return None
    from pci_planning_and_optimization.sftp.client import Config as SftpPoolConfig
    from pci_planning_and_optimization.sftp.client import SFTPClient

    return SFTPClient(
        None,
        SftpPoolConfig(
            enabled=True,
            timeout_seconds=sftp_cfg.timeout_seconds,
            max_idle_seconds=sftp_cfg.max_idle_seconds,
            cleanup_interval_seconds=sftp_cfg.cleanup_interval_seconds,
        ),
    )
