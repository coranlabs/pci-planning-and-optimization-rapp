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


def _local_name(tag: str) -> str:
    if tag.startswith("{"):
        return tag.partition("}")[2]
    return tag


def _children(elem: etree._Element, name: str) -> list[etree._Element]:
    return [c for c in elem if _local_name(c.tag) == name]


def _first_child(elem: etree._Element, name: str) -> etree._Element | None:
    for c in elem:
        if _local_name(c.tag) == name:
            return c
    return None


def _build_meas_collec_file(root: etree._Element) -> MeasCollecFile:
    header_el = _first_child(root, "fileHeader")
    file_header = FileHeader()
    if header_el is not None:
        sender_el = _first_child(header_el, "fileSender")
        collec_el = _first_child(header_el, "measCollec")
        file_header = FileHeader(
            fileFormatVersion=header_el.get("fileFormatVersion", ""),
            vendorName=header_el.get("vendorName", ""),
            file_sender=(
                FileSender(
                    localDn=sender_el.get("localDn", ""),
                    elementType=sender_el.get("elementType", ""),
                )
                if sender_el is not None
                else FileSender()
            ),
            meas_collec=(
                MeasCollec(beginTime=collec_el.get("beginTime", ""))
                if collec_el is not None
                else MeasCollec()
            ),
        )

    meas_data_list: list[MeasData] = []
    for md_el in _children(root, "measData"):
        me_el = _first_child(md_el, "managedElement")
        managed_element = (
            ManagedElement(
                localDn=me_el.get("localDn", ""),
                userLabel=me_el.get("userLabel", ""),
                swVersion=me_el.get("swVersion", ""),
            )
            if me_el is not None
            else ManagedElement()
        )

        meas_info_list: list[MeasInfo] = []
        for mi_el in _children(md_el, "measInfo"):
            gran_el = _first_child(mi_el, "granPeriod")
            gran_period = (
                GranPeriod(
                    duration=gran_el.get("duration", ""),
                    endTime=gran_el.get("endTime", ""),
                )
                if gran_el is not None
                else GranPeriod()
            )

            meas_types: list[MeasType] = []
            for mt_el in _children(mi_el, "measType"):
                p_attr = mt_el.get("p", "0")
                try:
                    p_val = int(p_attr)
                except ValueError:
                    p_val = 0
                meas_types.append(MeasType(p=p_val, name=(mt_el.text or "").strip()))

            meas_values: list[MeasValue] = []
            for mv_el in _children(mi_el, "measValue"):
                results: list[MeasResult] = []
                for r_el in _children(mv_el, "r"):
                    rp_attr = r_el.get("p", "0")
                    try:
                        rp_val = int(rp_attr)
                    except ValueError:
                        rp_val = 0
                    results.append(MeasResult(p=rp_val, value=r_el.text or ""))
                meas_values.append(
                    MeasValue(
                        measObjLdn=mv_el.get("measObjLdn", ""),
                        results=results,
                        suspect=mv_el.get("suspect", ""),
                    )
                )

            meas_info_list.append(
                MeasInfo(
                    measInfoId=mi_el.get("measInfoId", ""),
                    gran_period=gran_period,
                    meas_types=meas_types,
                    meas_values=meas_values,
                )
            )

        meas_data_list.append(
            MeasData(managed_element=managed_element, meas_info=meas_info_list)
        )

    return MeasCollecFile(file_header=file_header, meas_data=meas_data_list)


class XMLParser:

    __slots__ = ("_logger",)

    def __init__(self, logger: Logger | None = None) -> None:
        self._logger = logger if logger is not None else with_component("xml_parser")

    def parse(self, xml_data: bytes, filename: str = "") -> PMData:
        with trace_xml_parse(filename or ""):
            try:
                parser = etree.XMLParser(resolve_entities=False, no_network=True)
                root = etree.fromstring(xml_data, parser=parser)
            except etree.XMLSyntaxError as exc:
                raise new(
                    ErrorCategory.PARSE,
                    "XML_UNMARSHAL",
                    f"failed to unmarshal XML: {exc}",
                ).with_component("xml_parser").with_cause(exc) from exc
            except (ValueError, TypeError) as exc:
                raise new(
                    ErrorCategory.PARSE,
                    "XML_UNMARSHAL",
                    f"failed to unmarshal XML: {exc}",
                ).with_component("xml_parser").with_cause(exc) from exc

            if _local_name(root.tag) != "measCollecFile":
                err = new(
                    ErrorCategory.PARSE,
                    "XML_ROOT",
                    f"unexpected root element: {_local_name(root.tag)!r} "
                    "(expected 'measCollecFile')",
                ).with_component("xml_parser")
                raise err

            try:
                meas_file = _build_meas_collec_file(root)
            except Exception as exc:
                raise new(
                    ErrorCategory.PARSE,
                    "XML_UNMARSHAL",
                    f"failed to unmarshal XML: {exc}",
                ).with_component("xml_parser").with_cause(exc) from exc

            self._logger.with_fields(
                {
                    "fileFormat": meas_file.file_header.file_format_version,
                    "vendor": meas_file.file_header.vendor_name,
                    "source": meas_file.file_header.file_sender.local_dn,
                    "elementType": meas_file.file_header.file_sender.element_type,
                }
            ).debug("Parsing 3GPP PM XML file")

            pm_data = PMData(
                source_name=extract_source_name(
                    meas_file.file_header.file_sender.local_dn
                ),
                begin_time=meas_file.file_header.meas_collec.begin_time,
            )

            for meas_data in meas_file.meas_data:
                for meas_info in meas_data.meas_info:
                    pm_data.end_time = meas_info.gran_period.end_time
                    pm_data.granularity_period = meas_info.gran_period.duration

                    meas_type_map: dict[int, str] = {
                        mt.p: mt.name for mt in meas_info.meas_types
                    }

                    for meas_value in meas_info.meas_values:
                        sd, sst, ok = parse_meas_obj_ldn(meas_value.meas_obj_ldn)
                        if ok:
                            if pm_data.slice_sd == 0 and sd > 0:
                                pm_data.slice_sd = sd
                            if pm_data.slice_sst == 0 and sst > 0:
                                pm_data.slice_sst = sst
                            self._logger.with_fields(
                                {
                                    "slice_sd": sd,
                                    "slice_sst": sst,
                                    "measObjLdn": meas_value.meas_obj_ldn,
                                }
                            ).debug("[XML] Extracted slice identifier from PM data")

                        for result in meas_value.results:
                            meas_type_name = meas_type_map.get(result.p, "")
                            if meas_type_name == "":
                                continue

                            pm_data.per_object.setdefault(
                                meas_value.meas_obj_ldn, {}
                            )[meas_type_name] = result.value

                            try:
                                value = parse_float_value(result.value)
                            except ValueError:
                                self._logger.with_fields(
                                    {
                                        "measType": meas_type_name,
                                        "value": result.value,
                                    }
                                ).debug("[XML] Non-numeric measurement kept as text")
                                continue

                            pm_data.measurements[meas_type_name] = value

                            self._logger.with_fields(
                                {
                                    "measType": meas_type_name,
                                    "value": value,
                                    "object": meas_value.meas_obj_ldn,
                                }
                            ).debug("[XML] Extracted measurement")

            self._logger.with_fields(
                {
                    "source": pm_data.source_name,
                    "measurements": len(pm_data.measurements),
                }
            ).debug("[XML] Successfully parsed 3GPP PM data")

            if pm_data.measurements:
                self._logger.with_fields(
                    {
                        "source": pm_data.source_name,
                        "totalCount": len(pm_data.measurements),
                    }
                ).debug("[XML] PM measurement data extracted")
            else:
                self._logger.warn("[XML] No measurements found in XML file")

            return pm_data

