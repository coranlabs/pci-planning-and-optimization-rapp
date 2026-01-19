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
from typing import Any, Final, Self

import yaml
from pydantic import BaseModel, ConfigDict, Field, ValidationError

from pci_planning_and_optimization.errors import AppError, ErrorCategory, new
from pci_planning_and_optimization.logging_setup import with_component

__all__ = [
    "INSECURE_SSH_HOSTKEY_ENV",
    "Config",
    "load_config",
]


INSECURE_SSH_HOSTKEY_ENV: Final[str] = "RAPP_INSECURE_SSH_HOSTKEY"


_DEFAULT_CONFIG_PATH: Final[str] = "config/rapp_config.yaml"


class Config(BaseModel):

    model_config = ConfigDict(
        extra="ignore",
        populate_by_name=True,
        validate_assignment=True,
    )

    log_level: str = Field(default="Info", alias="log_level")
    node_id: str = Field(default="", alias="node_id")
    http_port: str = Field(default="8080", alias="http_port")

    sftp_enabled: bool = Field(default=False, alias="sftp_enabled")
    sftp_max_idle_time: int = Field(default=300, alias="sftp_max_idle_time")
    sftp_cleanup_interval: int = Field(default=60, alias="sftp_cleanup_interval")
    sftp_timeout: int = Field(default=30, alias="sftp_timeout")

    insecure_ssh_hostkey: bool = Field(default=False, alias="insecure_ssh_hostkey")

    @classmethod
    def load_config(cls, yaml_path: str | None = None) -> Self:
        return _load_config_impl(cls, yaml_path)


def load_config(yaml_path: str | None = None) -> Config:
    return Config.load_config(yaml_path)


def _load_config_impl(cls: type[Config], yaml_path: str | None) -> Config:
    log = with_component("config")

    if yaml_path is None:
        yaml_path = os.environ.get("CONFIG_PATH", _DEFAULT_CONFIG_PATH)

    yaml_data = _try_load_yaml(yaml_path, log)

    try:
        cfg = cls.model_validate(yaml_data) if yaml_data else cls()
    except ValidationError as exc:
        raise _config_error("CONFIG_INVALID_YAML", str(exc)) from exc

    cfg.log_level = _env("LOG_LEVEL", cfg.log_level)
    cfg.node_id = _env("NODE_ID", cfg.node_id)
    cfg.http_port = _env("HTTP_PORT", cfg.http_port)

    cfg.sftp_enabled = _is_truthy(os.environ.get("SFTP_ENABLED", "")) or (
        cfg.sftp_enabled and os.environ.get("SFTP_ENABLED", "") == ""
    )
    cfg.sftp_max_idle_time = _env_int("SFTP_MAX_IDLE_TIME", cfg.sftp_max_idle_time)
    cfg.sftp_cleanup_interval = _env_int(
        "SFTP_CLEANUP_INTERVAL", cfg.sftp_cleanup_interval
    )
    cfg.sftp_timeout = _env_int("SFTP_TIMEOUT", cfg.sftp_timeout)

    cfg.insecure_ssh_hostkey = _is_truthy(os.environ.get(INSECURE_SSH_HOSTKEY_ENV, ""))

    return cfg


def _try_load_yaml(path: str, log: Any) -> dict[str, Any]:
    try:
        text = Path(path).read_text(encoding="utf-8")
    except FileNotFoundError:
        return {}
    except OSError as exc:
        log.with_error(exc).with_field("path", path).warn(
            "[CONFIG] Could not read YAML; using environment only"
        )
        return {}
    try:
        loaded = yaml.safe_load(text)
    except yaml.YAMLError as exc:
        log.with_error(exc).with_field("path", path).warn(
            "[CONFIG] Failed to parse YAML; using environment only"
        )
        return {}
    if loaded is None:
        return {}
    if not isinstance(loaded, dict):
        log.with_field("path", path).warn(
            "[CONFIG] YAML root must be a mapping; ignoring file"
        )
        return {}
    return loaded


def _env(key: str, default: str) -> str:
    value = os.environ.get(key, "")
    return value if value else default


def _env_int(key: str, default: int) -> int:
    value = os.environ.get(key, "")
    if not value:
        return default
    try:
        return int(value)
    except (TypeError, ValueError):
        return default


_TRUTHY_VALUES: Final[frozenset[str]] = frozenset(
    {"1", "true", "yes", "on"}
)


def _is_truthy(value: str) -> bool:
    return value.strip().lower() in _TRUTHY_VALUES


def _config_error(code: str, message: str) -> AppError:
    return new(ErrorCategory.CONFIGURATION, code, message)
