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

import re
from dataclasses import dataclass, field
from typing import Final

from lxml import etree
from pydantic import BaseModel, ConfigDict, Field

from pci_planning_and_optimization.errors import ErrorCategory, new
from pci_planning_and_optimization.logging_setup import Logger, with_component
from pci_planning_and_optimization.tracing import trace_xml_parse


class _XmlModel(BaseModel):

    model_config = ConfigDict(populate_by_name=True, extra="ignore")


class FileSender(_XmlModel):

    local_dn: str = Field(default="", alias="localDn")
    element_type: str = Field(default="", alias="elementType")


class MeasCollec(_XmlModel):

    begin_time: str = Field(default="", alias="beginTime")


class FileHeader(_XmlModel):

    file_format_version: str = Field(default="", alias="fileFormatVersion")
    vendor_name: str = Field(default="", alias="vendorName")
    file_sender: FileSender = Field(default_factory=FileSender)
    meas_collec: MeasCollec = Field(default_factory=MeasCollec)


class ManagedElement(_XmlModel):

    local_dn: str = Field(default="", alias="localDn")
    user_label: str = Field(default="", alias="userLabel")
    sw_version: str = Field(default="", alias="swVersion")


class GranPeriod(_XmlModel):

    duration: str = Field(default="", alias="duration")
    end_time: str = Field(default="", alias="endTime")


class MeasType(_XmlModel):

    p: int = Field(default=0, alias="p")
    name: str = Field(default="")


class MeasResult(_XmlModel):

    p: int = Field(default=0, alias="p")
    value: str = Field(default="")


class MeasValue(_XmlModel):

    meas_obj_ldn: str = Field(default="", alias="measObjLdn")
    results: list[MeasResult] = Field(default_factory=list)
    suspect: str = Field(default="", alias="suspect")


class MeasInfo(_XmlModel):

    meas_info_id: str = Field(default="", alias="measInfoId")
    gran_period: GranPeriod = Field(default_factory=GranPeriod)
    meas_types: list[MeasType] = Field(default_factory=list)
    meas_values: list[MeasValue] = Field(default_factory=list)


class MeasData(_XmlModel):

    managed_element: ManagedElement = Field(default_factory=ManagedElement)
    meas_info: list[MeasInfo] = Field(default_factory=list)


class MeasCollecFile(_XmlModel):

    file_header: FileHeader = Field(default_factory=FileHeader)
    meas_data: list[MeasData] = Field(default_factory=list)


_UINT32_MAX: Final[int] = 2**32 - 1
_UINT8_MAX: Final[int] = 2**8 - 1


@dataclass
class PMData:

    source_name: str = ""
    begin_time: str = ""
    end_time: str = ""
    granularity_period: str = ""
    measurements: dict[str, float] = field(default_factory=dict)
    per_object: dict[str, dict[str, str]] = field(default_factory=dict)
    slice_sd: int = 0
    slice_sst: int = 0

    throughput_dl: float = 0.0
    throughput_ul: float = 0.0
    prb_used_dl: float = 0.0
    mean_active_ue_dl: float = 0.0
    max_active_ue_dl: float = 0.0
    mean_active_ue_ul: float = 0.0
    max_active_ue_ul: float = 0.0

    bler: float = 0.0
    cqi: float = 0.0
    hol_delay: float = 0.0

    sinr: float = 0.0
    retx_ratio: float = 0.0
    tx_buffer_bytes: float = 0.0

    def __post_init__(self) -> None:
        if not 0 <= int(self.slice_sd) <= _UINT32_MAX:
            raise ValueError(
                f"slice_sd {self.slice_sd!r} out of uint32 range [0, {_UINT32_MAX}]"
            )
        if not 0 <= int(self.slice_sst) <= _UINT8_MAX:
            raise ValueError(
                f"slice_sst {self.slice_sst!r} out of uint8 range [0, {_UINT8_MAX}]"
            )


_SLICE_RE: Final[re.Pattern[str]] = re.compile(r"Slice\[([^\]]*)\]")


def parse_float_value(s: str) -> float:
    s = s.strip()
    if s == "":
        return 0.0
    return float(s)


def extract_source_name(local_dn: str) -> str:
    if "=" in local_dn:
        parts = local_dn.split("=")
        if len(parts) > 1:
            return parts[1]
    return local_dn


def parse_meas_obj_ldn(meas_obj_ldn: str) -> tuple[int, int, bool]:
    if "Slice[" not in meas_obj_ldn:
        return 0, 0, False

    match = _SLICE_RE.search(meas_obj_ldn)
    if match is None:
        return 0, 0, False

    sd = 0
    sst = 0
    for part in match.group(1).split(","):
        if "=" not in part:
            continue
        key, _, value = part.partition("=")
        key = key.strip()
        value = value.strip()
        if key == "sd":
            try:
                sd_val = int(value, 10)
            except ValueError:
                continue
            if 0 <= sd_val <= _UINT32_MAX:
                sd = sd_val
        elif key == "sst":
            try:
                sst_val = int(value, 10)
            except ValueError:
                continue
            if 0 <= sst_val <= _UINT8_MAX:
                sst = sst_val

    return sd, sst, (sd > 0 or sst > 0)


