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

from typing import Final

MEAS_KPI:              Final[str] = "kpi"
MEAS_CELL_HO:          Final[str] = "cell_ho"
MEAS_RELATION_HO:      Final[str] = "relation_ho"
MEAS_CONFLICT_COUNT:   Final[str] = "conflict_count"
MEAS_OPTIMIZATION_RUN: Final[str] = "optimization_run"

ALL_MEASUREMENTS: Final[tuple[str, ...]] = (
    MEAS_KPI,
    MEAS_CELL_HO,
    MEAS_RELATION_HO,
    MEAS_CONFLICT_COUNT,
    MEAS_OPTIMIZATION_RUN,
)


FIELD_KPI_ACTIVE_CELLS:       Final[str] = "active_cells"
FIELD_KPI_ACTIVE_CONFLICTS:   Final[str] = "active_conflicts"
FIELD_KPI_HO_SUCCESS_RATE:    Final[str] = "ho_success_rate"
FIELD_KPI_PENDING_DECISIONS:  Final[str] = "pending_decisions"


TAG_CELL_ID:        Final[str] = "cell_id"
TAG_TECHNOLOGY:     Final[str] = "technology"
TAG_MO_CLASS:       Final[str] = "mo_class"

FIELD_CELL_HO_ATTEMPTS:    Final[str] = "ho_attempts_total"
FIELD_CELL_HO_SUCCESSES:   Final[str] = "ho_successes_total"
FIELD_CELL_HO_SUCCESS_RATE: Final[str] = "ho_success_rate"
FIELD_CELL_PCI:            Final[str] = "pci"
FIELD_CELL_SHORT:          Final[str] = "cell_short"


TAG_SOURCE_CELL_ID: Final[str] = "source_cell_id"
TAG_TARGET_CELL_ID: Final[str] = "target_cell_id"

FIELD_REL_HO_ATTEMPTS:     Final[str] = "ho_attempts"
FIELD_REL_HO_SUCCESSES:    Final[str] = "ho_successes"
FIELD_REL_HO_FAILURES:     Final[str] = "ho_failures"
FIELD_REL_HO_FAILURE_RATE: Final[str] = "ho_failure_rate"


TAG_CONFLICT_CLASS:    Final[str] = "class"
TAG_CONFLICT_SEVERITY: Final[str] = "severity"

FIELD_CONFLICT_COUNT: Final[str] = "count"


TAG_RUN_ID: Final[str] = "run_id"
TAG_STATUS: Final[str] = "status"

FIELD_RUN_N_CHANGES:               Final[str] = "n_changes"
FIELD_RUN_N_CELLS:                 Final[str] = "n_cells"
FIELD_RUN_PASSES_EXECUTED:         Final[str] = "passes_executed"
FIELD_RUN_FINAL_SOFT_COST:         Final[str] = "final_soft_cost"
FIELD_RUN_PREDICTED_AVOIDED_PER_WEEK: Final[str] = "predicted_avoided_per_week"
FIELD_RUN_CONVERGED:               Final[str] = "converged"


TREND_METRICS: Final[dict[str, tuple[str, str]]] = {
    "active_cells":      (MEAS_KPI, FIELD_KPI_ACTIVE_CELLS),
    "active_conflicts":  (MEAS_KPI, FIELD_KPI_ACTIVE_CONFLICTS),
    "ho_success_rate":   (MEAS_KPI, FIELD_KPI_HO_SUCCESS_RATE),
    "pending_decisions": (MEAS_KPI, FIELD_KPI_PENDING_DECISIONS),
}
