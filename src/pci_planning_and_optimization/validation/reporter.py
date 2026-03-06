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

from datetime import UTC, datetime
from typing import Any

from pci_planning_and_optimization.validation.ho_metrics import HoValidationReport


def render_dashboard_markdown(
    reports: dict[str, HoValidationReport],
    *,
    title: str = "PCI Handover Failure Reduction — Plan Health",
    recommendations_by_tech: dict[str, list[dict[str, Any]]] | None = None,
) -> str:
    out: list[str] = []
    out.append(f"# {title}")
    out.append("")
    out.append(f"_Generated: {datetime.now(UTC).isoformat(timespec='seconds')}_")
    out.append("")

    if not reports:
        out.append("_No technologies reported._")
        return "\n".join(out)

    for tech in ("lte", "nr"):
        if tech not in reports:
            continue
        out.append("---")
        out.append("")
        out.extend(_render_tech_section(
            reports[tech],
            recommendations_by_tech.get(tech) if recommendations_by_tech else None,
        ))

    return "\n".join(out)


def _render_tech_section(
    report: HoValidationReport,
    recommendations: list[dict[str, Any]] | None = None,
) -> list[str]:
    out: list[str] = []
    out.append(f"## {report.technology.upper()} Plan Health")
    out.append("")

    if report.skipped:
        out.append(f"**Skipped** — {report.skip_reason}")
        out.append("")
        return out

    out.extend(_render_ho_impact(report))
    out.extend(_render_hard_constraints(report))
    out.extend(_render_soft_constraints(report))
    out.extend(_render_palette(report))
    out.extend(_render_reuse_distance(report))
    out.extend(_render_changes(report, recommendations))
    return out


