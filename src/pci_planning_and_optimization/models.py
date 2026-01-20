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

from datetime import datetime
from enum import Enum
from math import asin, cos, radians, sin, sqrt

from pydantic import BaseModel, field_validator, model_validator


class Technology(str, Enum):

    LTE = "lte"
    NR = "nr"


class RelationSource(str, Enum):

    REAL = "real"
    SHADOW = "shadow"


ALLOWED_CELL_TYPES: tuple[str, ...] = ("macro", "small", "das", "indoor")


_LTE_MO_CLASSES: set[str] = {"EUtranCellFDD", "EUtranCellTDD"}
_NR_MO_CLASSES: set[str] = {"NRCellDU"}


class Cell(BaseModel):

    id: str
    technology: Technology
    mo_class: str

    dn: str | None = None

    pci: int
    pci_components: tuple[int, int] | None = None

    duplex: str | None = None
    earfcn_dl: int | None = None
    earfcn_ul: int | None = None
    arfcn_dl: int | None = None
    arfcn_ul: int | None = None

    bandwidth_mhz: int | None = None
    tac: int | None = None
    plmn_mcc: str | None = None
    plmn_mnc: str | None = None

    lat: float | None = None
    lon: float | None = None
    azimuth: float | None = None
    antenna_height: float | None = None

    region: str | None = None
    band: int | None = None

    cell_type: str
    prb_util: float | None = None

    thp_dl_kbps: float | None = None
    thp_ul_kbps: float | None = None
    active_ues: int | None = None
    cqi: float | None = None
    sinr_db: float | None = None
    bler_dl: float | None = None

    ho_attempts_total: int = 0
    ho_successes_total: int = 0

    network_pci_conflict_flag: bool | None = None


    @field_validator("cell_type")
    @classmethod
    def _validate_cell_type(cls, v: str) -> str:
        if v not in ALLOWED_CELL_TYPES:
            raise ValueError(f"cell_type must be one of {ALLOWED_CELL_TYPES}, got {v!r}")
        return v

    @field_validator("duplex")
    @classmethod
    def _validate_duplex(cls, v: str | None) -> str | None:
        if v is None:
            return v
        if v not in {"FDD", "TDD"}:
            raise ValueError(f"duplex must be 'FDD' or 'TDD', got {v!r}")
        return v

    @field_validator("prb_util")
    @classmethod
    def _validate_prb_util(cls, v: float | None) -> float | None:
        if v is None:
            return v
        if not (0.0 <= v <= 1.0):
            raise ValueError(f"prb_util must be in [0.0, 1.0], got {v}")
        return v

    @model_validator(mode="after")
    def _validate_tech_fields(self) -> Cell:
        pci_max = 503 if self.technology == Technology.LTE else 1007
        if not (0 <= self.pci <= pci_max):
            raise ValueError(
                f"PCI {self.pci} out of range for {self.technology.value}: "
                f"expected 0..{pci_max}"
            )

        valid_mos = _LTE_MO_CLASSES if self.technology == Technology.LTE else _NR_MO_CLASSES
        if self.mo_class not in valid_mos:
            raise ValueError(
                f"mo_class {self.mo_class!r} is not valid for {self.technology.value} "
                f"(expected one of {sorted(valid_mos)})"
            )

        if self.technology == Technology.LTE:
            if self.pci_components is None:
                raise ValueError(
                    f"LTE cell {self.id!r}: pci_components is required "
                    "(NCMP write needs physicalLayerCellIdGroup + physicalLayerSubCellId)"
                )
            grp, sub = self.pci_components
            if not (0 <= grp <= 167) or not (0 <= sub <= 2):
                raise ValueError(
                    f"LTE pci_components={self.pci_components}: "
                    "group must be 0..167 and sub must be 0..2"
                )
            if grp * 3 + sub != self.pci:
                raise ValueError(
                    f"LTE pci={self.pci} but pci_components={self.pci_components} "
                    f"compose to {grp * 3 + sub}"
                )
            if self.mo_class == "EUtranCellFDD" and self.duplex != "FDD":
                raise ValueError(
                    f"EUtranCellFDD requires duplex='FDD', got {self.duplex!r}"
                )
            if self.mo_class == "EUtranCellTDD" and self.duplex != "TDD":
                raise ValueError(
                    f"EUtranCellTDD requires duplex='TDD', got {self.duplex!r}"
                )
            if self.arfcn_dl is not None or self.arfcn_ul is not None:
                raise ValueError(
                    f"LTE cell {self.id!r} must not specify arfcn_dl/arfcn_ul (NR-only fields)"
                )
            if self.mo_class == "EUtranCellFDD" and self.earfcn_ul is None:
                raise ValueError(
                    f"EUtranCellFDD cell {self.id!r}: earfcn_ul is required for FDD"
                )
            if self.mo_class == "EUtranCellTDD" and self.earfcn_ul is not None:
                raise ValueError(
                    f"EUtranCellTDD cell {self.id!r}: earfcn_ul must be empty for TDD "
                    "(use the single earfcn_dl field)"
                )

        elif self.technology == Technology.NR:
            if self.pci_components is not None:
                raise ValueError(
                    f"NR cell {self.id!r}: pci_components must be empty (LTE-only)"
                )
            if self.duplex is not None:
                raise ValueError(
                    f"NR cell {self.id!r}: duplex must be empty (LTE-only)"
                )
            if self.earfcn_dl is not None or self.earfcn_ul is not None:
                raise ValueError(
                    f"NR cell {self.id!r}: earfcn_* fields are LTE-only; "
                    "use arfcn_dl / arfcn_ul instead"
                )

        return self


    def primary_frequency(self) -> int | None:
        if self.technology == Technology.LTE:
            return self.earfcn_dl
        return self.arfcn_dl


class NeighborRelation(BaseModel):

    source_cell_id: str
    target_cell_id: str
    ho_attempts: int = 0
    ho_successes: int = 0
    ho_failures: int = 0
    ho_prep_failures: int = 0
    is_x2_xn: bool = True
    cross_technology: bool = False
    relation_source: RelationSource = RelationSource.REAL
    last_seen: datetime | None = None

    @model_validator(mode="after")
    def _validate_counters(self) -> NeighborRelation:
        if self.source_cell_id == self.target_cell_id:
            raise ValueError(
                f"NeighborRelation source==target for cell {self.source_cell_id!r}"
            )
        if self.ho_attempts < 0 or self.ho_successes < 0 or self.ho_failures < 0:
            raise ValueError("HO counters must be non-negative")
        if self.ho_successes + self.ho_failures > self.ho_attempts:
            raise ValueError(
                f"HO bookkeeping: successes ({self.ho_successes}) + failures "
                f"({self.ho_failures}) > attempts ({self.ho_attempts})"
            )
        return self


def _haversine_m(lat1: float, lon1: float, lat2: float, lon2: float) -> float:
    earth_r = 6_371_008.8
    phi1, phi2 = radians(lat1), radians(lat2)
    dphi = radians(lat2 - lat1)
    dlam = radians(lon2 - lon1)
    a = sin(dphi / 2) ** 2 + cos(phi1) * cos(phi2) * sin(dlam / 2) ** 2
    return 2 * earth_r * asin(sqrt(a))


def _shadow_threshold_for_pair(
    type_a: str, type_b: str, thresholds: dict[str, float]
) -> float:
    if type_a in {"indoor", "das"} or type_b in {"indoor", "das"}:
        return thresholds["indoor_any"]
    if type_a == "macro" and type_b == "macro":
        return thresholds["macro_macro"]
    if {type_a, type_b} == {"macro", "small"}:
        return thresholds["macro_small"]
    if type_a == "small" and type_b == "small":
        return thresholds["small_small"]
    return thresholds["macro_macro"]


