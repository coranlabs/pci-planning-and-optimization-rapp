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


@dataclass
class InfluxWriter:

    cfg: InfluxConfig
    _client: Any = field(default=None, init=False, repr=False)
    _write_api: Any = field(default=None, init=False, repr=False)
    _enabled_at_runtime: bool = field(default=False, init=False)
    _write_errors: int = field(default=0, init=False)
    _writes_ok: int = field(default=0, init=False)
    _last_error: str | None = field(default=None, init=False)

    def __post_init__(self) -> None:
        if not _influx_configured(self.cfg, "InfluxWriter"):
            return
        try:
            from influxdb_client import InfluxDBClient
            from influxdb_client.client.write_api import (
                WriteOptions,
                WriteType,
            )
        except ImportError as e:
            _log.warning(
                "InfluxWriter: influxdb-client not installed (%s) — Influx writes disabled. "
                "Install with `pip install influxdb-client`.", e,
            )
            return

        try:
            self._client = InfluxDBClient(
                url=self.cfg.url,
                token=self.cfg.token,
                org=self.cfg.org,
                timeout=int(self.cfg.write_timeout_s * 1000),
                enable_gzip=True,
            )
            self._write_api = self._client.write_api(
                write_options=WriteOptions(
                    write_type=WriteType.batching,
                    batch_size=self.cfg.batch_size,
                    flush_interval=self.cfg.flush_interval_ms,
                    jitter_interval=2_000,
                    retry_interval=5_000,
                    max_retries=3,
                    max_retry_delay=30_000,
                    exponential_base=2,
                )
            )
            self._enabled_at_runtime = True
            _log.info(
                "InfluxWriter: ready — url=%s org=%s bucket=%s batch=%d flush=%dms",
                self.cfg.url, self.cfg.org, self.cfg.bucket,
                self.cfg.batch_size, self.cfg.flush_interval_ms,
            )
        except Exception as e:
            _log.warning("InfluxWriter: init failed (%s: %s) — writes disabled", type(e).__name__, e)
            self._client = None
            self._write_api = None


    @property
    def enabled(self) -> bool:
        return self._enabled_at_runtime

    def write_auth_user(self, username: str, password_hash: str) -> None:
        if not self._enabled_at_runtime or self._client is None:
            return
        try:
            from influxdb_client import Point
            from influxdb_client.client.write_api import SYNCHRONOUS

            point = Point("auth_user").tag("username", username).field("hash", password_hash)
            with self._client.write_api(write_options=SYNCHRONOUS) as api:
                api.write(bucket=self.cfg.bucket, org=self.cfg.org, record=point)
            self._writes_ok += 1
        except Exception as e:
            self._write_errors += 1
            self._last_error = f"{type(e).__name__}: {e}"
            _log.warning("InfluxWriter: auth_user write failed (%s)", self._last_error)

    def stats(self) -> dict[str, Any]:
        return {
            "enabled": self._enabled_at_runtime,
            "writes_ok": self._writes_ok,
            "write_errors": self._write_errors,
            "last_error": self._last_error,
        }

    def close(self) -> None:
        try:
            if self._write_api is not None:
                self._write_api.close()
        except Exception:
            pass
        try:
            if self._client is not None:
                self._client.close()
        except Exception:
            pass
        self._enabled_at_runtime = False


    def record_kpis(self, kpis: dict[str, Any]) -> None:
        if not self._enabled_at_runtime:
            return
        fields: dict[str, Any] = {}
        if kpis.get("active_cells") is not None:
            fields[S.FIELD_KPI_ACTIVE_CELLS] = int(kpis["active_cells"])
        if kpis.get("active_conflicts") is not None:
            fields[S.FIELD_KPI_ACTIVE_CONFLICTS] = int(kpis["active_conflicts"])
        if kpis.get("ho_success_rate") is not None:
            fields[S.FIELD_KPI_HO_SUCCESS_RATE] = float(kpis["ho_success_rate"])
        if kpis.get("pending_decisions") is not None:
            fields[S.FIELD_KPI_PENDING_DECISIONS] = int(kpis["pending_decisions"])
        if not fields:
            return
        self._write_point(S.MEAS_KPI, tags={}, fields=fields)

    def record_network(self, network) -> None:
        if not self._enabled_at_runtime or self.cfg.skip_per_cell_series:
            return
        if network is None:
            return
        try:
            pass
        except Exception:
            pass
        for cell in network.cells.values():
            attempts = int(cell.ho_attempts_total or 0)
            successes = int(cell.ho_successes_total or 0)
            rate = (successes / attempts) if attempts else None
            short = _short_cell_id(cell.id)
            fields = {
                S.FIELD_CELL_HO_ATTEMPTS: attempts,
                S.FIELD_CELL_HO_SUCCESSES: successes,
                S.FIELD_CELL_PCI: int(cell.pci),
                S.FIELD_CELL_SHORT: short,
            }
            if rate is not None:
                fields[S.FIELD_CELL_HO_SUCCESS_RATE] = float(rate)
            self._write_point(
                S.MEAS_CELL_HO,
                tags={
                    S.TAG_CELL_ID: cell.id,
                    S.TAG_TECHNOLOGY: cell.technology.value,
                    S.TAG_MO_CLASS: cell.mo_class,
                },
                fields=fields,
            )
        for r in network.relations:
            attempts = int(r.ho_attempts or 0)
            successes = int(r.ho_successes or 0)
            failures = int(r.ho_failures or 0)
            rate = (failures / attempts) if attempts else None
            src = network.cells.get(r.source_cell_id)
            tech = src.technology.value if src else "unknown"
            fields = {
                S.FIELD_REL_HO_ATTEMPTS: attempts,
                S.FIELD_REL_HO_SUCCESSES: successes,
                S.FIELD_REL_HO_FAILURES: failures,
            }
            if rate is not None:
                fields[S.FIELD_REL_HO_FAILURE_RATE] = float(rate)
            self._write_point(
                S.MEAS_RELATION_HO,
                tags={
                    S.TAG_SOURCE_CELL_ID: r.source_cell_id,
                    S.TAG_TARGET_CELL_ID: r.target_cell_id,
                    S.TAG_TECHNOLOGY: tech,
                },
                fields=fields,
            )

    def record_conflict_summary(self, summary_by_tech: dict[str, dict[str, Any]]) -> None:
        if not self._enabled_at_runtime:
            return
        for tech, vals in summary_by_tech.items():
            if not isinstance(vals, dict):
                continue
            collisions = int(vals.get("collisions", 0) or 0)
            confusions = int(vals.get("confusions", 0) or 0)
            total = int(vals.get("conflicts", 0) or 0)
            minor = max(0, total - collisions - confusions)
            for cls, severity, count in (
                ("collision", "critical", collisions),
                ("confusion", "major",    confusions),
                ("minor",     "minor",    minor),
            ):
                self._write_point(
                    S.MEAS_CONFLICT_COUNT,
                    tags={
                        S.TAG_TECHNOLOGY: tech,
                        S.TAG_CONFLICT_CLASS: cls,
                        S.TAG_CONFLICT_SEVERITY: severity,
                    },
                    fields={S.FIELD_CONFLICT_COUNT: count},
                )

    def record_optimization_run(self, run_dict: dict[str, Any]) -> None:
        if not self._enabled_at_runtime:
            return
        try:
            run_id = str(run_dict.get("run_id") or "")
            if not run_id:
                return
            tech = str(run_dict.get("technology") or "")
            status = str(run_dict.get("status") or "pending")
            n_changes = len(run_dict.get("changes") or [])
            n_cells = int(run_dict.get("n_cells") or 0)
            passes = int(run_dict.get("passes_executed") or 0)
            soft = float(run_dict.get("final_soft_cost") or 0.0)
            converged = 1 if run_dict.get("converged") else 0
            avoided = sum(
                float(c.get("predicted_ho_failures_avoided_per_week") or 0.0)
                for c in run_dict.get("changes") or []
            )
            self._write_point(
                S.MEAS_OPTIMIZATION_RUN,
                tags={
                    S.TAG_TECHNOLOGY: tech,
                    S.TAG_RUN_ID: run_id,
                    S.TAG_STATUS: status,
                },
                fields={
                    S.FIELD_RUN_N_CHANGES: n_changes,
                    S.FIELD_RUN_N_CELLS: n_cells,
                    S.FIELD_RUN_PASSES_EXECUTED: passes,
                    S.FIELD_RUN_FINAL_SOFT_COST: soft,
                    S.FIELD_RUN_PREDICTED_AVOIDED_PER_WEEK: avoided,
                    S.FIELD_RUN_CONVERGED: converged,
                },
            )
        except Exception as e:
            self._note_error("record_optimization_run", e)


