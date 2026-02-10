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

import os
from pathlib import Path

import yaml
from pydantic import BaseModel, Field, field_validator

_LTE_VALID_MODS = {"mod3", "mod6", "mod30"}
_NR_VALID_MODS = {"mod3", "mod4", "mod30"}


class HypothesisConfig(BaseModel):

    min_correlation_ratio: float = 2.0


class LteScoringConfig(BaseModel):

    mod_priority: list[str] = Field(default_factory=lambda: ["mod3", "mod30"])
    enable_mod6: bool = False

    @field_validator("mod_priority")
    @classmethod
    def _validate_mods(cls, v: list[str]) -> list[str]:
        for m in v:
            if m not in _LTE_VALID_MODS:
                raise ValueError(
                    f"LTE mod_priority entry must be one of {sorted(_LTE_VALID_MODS)}, got {m!r}"
                )
        if len(set(v)) != len(v):
            raise ValueError(f"LTE mod_priority has duplicates: {v}")
        return v


class NrScoringConfig(BaseModel):

    mod_priority: list[str] = Field(default_factory=lambda: ["mod3", "mod4", "mod30"])

    @field_validator("mod_priority")
    @classmethod
    def _validate_mods(cls, v: list[str]) -> list[str]:
        for m in v:
            if m not in _NR_VALID_MODS:
                raise ValueError(
                    f"NR mod_priority entry must be one of {sorted(_NR_VALID_MODS)}, got {m!r}"
                )
        if len(set(v)) != len(v):
            raise ValueError(f"NR mod_priority has duplicates: {v}")
        return v


class ScoringConfig(BaseModel):
    lte: LteScoringConfig = Field(default_factory=LteScoringConfig)
    nr: NrScoringConfig = Field(default_factory=NrScoringConfig)
    headroom_hops: int = 5


class DistanceThresholds(BaseModel):

    macro_macro: int = 3000
    macro_small: int = 1500
    small_small: int = 500
    indoor_any: int = 200


class ShadowNrtConfig(BaseModel):
    enabled: bool = True
    distance_thresholds_m: DistanceThresholds = Field(default_factory=DistanceThresholds)
    require_same_frequency: bool = True
    require_same_technology: bool = True


class ConvergenceConfig(BaseModel):
    max_passes: int = 5
    min_soft_cost_improvement: float = 0.01
    per_pass_budget_pct: float = 0.005
    per_run_budget_pct: float = 0.01
    max_absolute_changes: int = 50


class TechPools(BaseModel):

    macro: list[int] = Field(default_factory=list)
    small: list[int] = Field(default_factory=list)
    indoor: list[int] = Field(default_factory=list)
    reserved: list[int] = Field(default_factory=list)

    @field_validator("macro", "small", "indoor", "reserved")
    @classmethod
    def _validate_range(cls, v: list[int]) -> list[int]:
        if not v:
            return v
        if len(v) != 2:
            raise ValueError(f"Pool range must be empty or [start, end], got {v}")
        if v[0] < 0 or v[1] <= v[0]:
            raise ValueError(f"Pool range must satisfy 0 <= start < end, got {v}")
        return v


class PoolsConfig(BaseModel):
    lte: TechPools = Field(default_factory=TechPools)
    nr: TechPools = Field(default_factory=TechPools)


class RollbackConfig(BaseModel):
    hosr_drop_threshold_pp: float = 1.0
    monitor_window_hours: int = 24


class SdnrConfig(BaseModel):

    enabled: bool = False
    base_url: str = ""
    username: str = ""
    password: str = ""
    netconf_node_id: str = ""
    function_id: str = "1"
    timeout_s: float = 30.0


class OscKafkaConfig(BaseModel):

    brokers: str = "onap-strimzi-kafka-bootstrap.onap.svc.cluster.local:9092"
    topic: str = "unauthenticated.SEC_3GPP_PERFORMANCEASSURANCE_OUTPUT"
    group_id: str = "pci-planning-rapp"
    username: str = ""
    password: str = ""
    security_protocol: str = "SASL_PLAINTEXT"


class OscSftpConfig(BaseModel):

    enabled: bool = True
    timeout_seconds: float = 30.0
    max_idle_seconds: float = 300.0
    cleanup_interval_seconds: float = 60.0


class OscConfig(BaseModel):

    kafka: OscKafkaConfig = Field(default_factory=OscKafkaConfig)
    sftp: OscSftpConfig = Field(default_factory=OscSftpConfig)
    pm_directory: str = ""
    max_files_per_refresh: int = 5000


class InfluxConfig(BaseModel):

    enabled: bool = False
    url: str = "http://localhost:8087"
    token: str = ""
    org: str = "pci-rapp"
    bucket: str = "pci_planning_and_optimization"
    write_timeout_s: float = 5.0
    batch_size: int = 500
    flush_interval_ms: int = 10000
    skip_per_cell_series: bool = False


class AppConfig(BaseModel):

    hypothesis: HypothesisConfig = Field(default_factory=HypothesisConfig)
    scoring: ScoringConfig = Field(default_factory=ScoringConfig)
    shadow_nrt: ShadowNrtConfig = Field(default_factory=ShadowNrtConfig)
    convergence: ConvergenceConfig = Field(default_factory=ConvergenceConfig)
    pools: PoolsConfig = Field(default_factory=PoolsConfig)
    rollback: RollbackConfig = Field(default_factory=RollbackConfig)
    sdnr: SdnrConfig = Field(default_factory=SdnrConfig)
    osc: OscConfig = Field(default_factory=OscConfig)
    influxdb: InfluxConfig = Field(default_factory=InfluxConfig)
    history_file: str = ""


PLACEHOLDER_PREFIX = "REPLACE_WITH"


def unfilled(cfg: AppConfig) -> list[str]:
    gaps: list[str] = []

    def needs(value: str, env: str, effect: str) -> None:
        v = (value or "").strip()
        if not v or v.startswith(PLACEHOLDER_PREFIX):
            gaps.append(f"{env} — {effect}")

    if not cfg.osc.pm_directory:
        needs(cfg.osc.kafka.brokers, "KAFKA_BROKERS", "no PM files are ingested")
        if cfg.osc.kafka.username:
            needs(cfg.osc.kafka.password, "KAFKA_PASSWORD", "the Kafka consumer cannot authenticate")
    if cfg.sdnr.enabled:
        needs(cfg.sdnr.base_url, "SDNR_BASE_URL", "approved PCI changes are not written back")
        needs(cfg.sdnr.username, "SDNR_USERNAME", "approved PCI changes are not written back")
        needs(cfg.sdnr.password, "SDNR_PASSWORD", "approved PCI changes are not written back")
    if cfg.influxdb.enabled:
        needs(cfg.influxdb.token, "INFLUX_TOKEN", "time-series storage is disabled")
    return gaps


def load_config(path: str | Path) -> AppConfig:
    p = Path(path)
    if not p.exists():
        raise FileNotFoundError(f"Config file not found: {p}")
    with p.open("r", encoding="utf-8") as f:
        raw = yaml.safe_load(f) or {}
    cfg = AppConfig.model_validate(raw)
    _apply_env_overrides(cfg)
    return cfg


def _apply_env_overrides(cfg: AppConfig) -> None:
    for env_name, target, attr in (
        ("KAFKA_BROKERS", cfg.osc.kafka, "brokers"),
        ("KAFKA_TOPIC", cfg.osc.kafka, "topic"),
        ("KAFKA_GROUP_ID", cfg.osc.kafka, "group_id"),
        ("KAFKA_USERNAME", cfg.osc.kafka, "username"),
        ("KAFKA_PASSWORD", cfg.osc.kafka, "password"),
        ("KAFKA_SECURITY_PROTOCOL", cfg.osc.kafka, "security_protocol"),
        ("PM_DIRECTORY", cfg.osc, "pm_directory"),
        ("PCI_HISTORY_FILE", cfg, "history_file"),
        ("SDNR_BASE_URL", cfg.sdnr, "base_url"),
        ("SDNR_USERNAME", cfg.sdnr, "username"),
        ("SDNR_PASSWORD", cfg.sdnr, "password"),
        ("SDNR_NETCONF_NODE_ID", cfg.sdnr, "netconf_node_id"),
        ("SDNR_FUNCTION_ID", cfg.sdnr, "function_id"),
    ):
        v = os.getenv(env_name)
        if v:
            setattr(target, attr, v)

    v = os.getenv("SDNR_ENABLED")
    if v:
        cfg.sdnr.enabled = v.lower() in {"1", "true", "yes", "on"}

    v = os.getenv("INFLUX_URL")
    if v:
        cfg.influxdb.url = v
    v = os.getenv("INFLUX_TOKEN")
    if v:
        cfg.influxdb.token = v
    v = os.getenv("INFLUX_ORG")
    if v:
        cfg.influxdb.org = v
    v = os.getenv("INFLUX_BUCKET")
    if v:
        cfg.influxdb.bucket = v
    v = os.getenv("INFLUX_ENABLED")
    if v:
        cfg.influxdb.enabled = v.lower() in {"1", "true", "yes", "on"}
