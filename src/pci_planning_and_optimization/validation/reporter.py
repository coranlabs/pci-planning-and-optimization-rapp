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


def _render_ho_impact(report: HoValidationReport) -> list[str]:
    out: list[str] = []
    out.append("### HO Impact")
    out.append("")
    out.append("| Metric | Value |")
    out.append("|---|---|")
    out.append(
        f"| Predicted HO failures avoided / week | "
        f"~{report.predicted_ho_failures_avoided_per_period:.0f} (estimate) |"
    )
    out.append(
        f"| Projected HOSR delta (lower bound) | "
        f"+{report.projected_hosr_delta_pp_lower_bound:.3f} pp |"
    )
    out.append(
        f"| Recommendations | {report.n_recommendations} "
        f"({report.churn_pct:.2f}% of network) |"
    )
    out.append("")
    return out


def _check_arrow(before: int, after: int) -> str:
    if after < before:
        return "down"
    if after > before:
        return "UP"
    return "flat"


def _render_hard_constraints(report: HoValidationReport) -> list[str]:
    b, a = report.before, report.after
    out: list[str] = []
    out.append("### Hard Constraints")
    out.append("")
    out.append("| Class | Before | After | Direction |")
    out.append("|---|---|---|---|")
    out.append(
        f"| Collisions | {b.n_collisions} | {a.n_collisions} | "
        f"{_check_arrow(b.n_collisions, a.n_collisions)} |"
    )
    out.append(
        f"| Confusions | {b.n_confusions} | {a.n_confusions} | "
        f"{_check_arrow(b.n_confusions, a.n_confusions)} |"
    )
    out.append("")
    return out


def _render_soft_constraints(report: HoValidationReport) -> list[str]:
    b, a = report.before, report.after
    out: list[str] = []
    out.append("### Soft Constraints (per-mod-N counts include collision pairs)")
    out.append("")
    out.append("| Class | Before | After | Direction |")
    out.append("|---|---|---|---|")
    out.append(
        f"| mod-3 | {b.n_mod3} | {a.n_mod3} | "
        f"{_check_arrow(b.n_mod3, a.n_mod3)} |"
    )
    if report.technology == "nr":
        out.append(
            f"| mod-4 | {b.n_mod4} | {a.n_mod4} | "
            f"{_check_arrow(b.n_mod4, a.n_mod4)} |"
        )
    out.append(
        f"| mod-30 | {b.n_mod30} | {a.n_mod30} | "
        f"{_check_arrow(b.n_mod30, a.n_mod30)} |"
    )
    if report.technology == "lte" and (b.n_mod6 + a.n_mod6) > 0:
        out.append(
            f"| mod-6 (opt-in) | {b.n_mod6} | {a.n_mod6} | "
            f"{_check_arrow(b.n_mod6, a.n_mod6)} |"
        )
    out.append("")
    return out


def _render_palette(report: HoValidationReport) -> list[str]:
    p_before = report.palette_before
    p_after = report.palette_after
    out: list[str] = []
    out.append("### Palette Utilization")
    out.append("")
    out.append(
        f"PCIs in use (before): **{p_before.n_unique_pcis}** / {p_before.pool_size}  "
        f"({p_before.utilization_pct:.1f}%)"
    )
    out.append(
        f"PCIs in use (after):  **{p_after.n_unique_pcis}** / {p_after.pool_size}  "
        f"({p_after.utilization_pct:.1f}%)"
    )
    out.append("")
    out.append("Mod-3 class distribution (after):")
    out.append("")
    out.append("| Class | Cells |")
    out.append("|---|---|")
    for k in sorted(p_after.mod3_class_counts.keys()):
        out.append(f"| mod-3 = {k} | {p_after.mod3_class_counts[k]} |")
    out.append("")
    out.append(f"Imbalance ratio (max / min, lower is better): {p_after.mod3_imbalance:.3f}")
    out.append("")
    return out


def _render_reuse_distance(report: HoValidationReport) -> list[str]:
    r_before = report.reuse_distance_before
    r_after = report.reuse_distance_after
    out: list[str] = []
    out.append("### Reuse Distance")
    out.append("")
    if r_before.n_reused_pcis == 0 and r_after.n_reused_pcis == 0:
        out.append("_No PCI is reused across cells with known coordinates._")
        out.append("")
        return out

    out.append("| Metric | Before | After |")
    out.append("|---|---|---|")
    out.append(
        f"| PCIs reused on ≥2 cells | {r_before.n_reused_pcis} | "
        f"{r_after.n_reused_pcis} |"
    )
    out.append(
        f"| Min reuse distance (m) | "
        f"{_fmt_distance(r_before.min_distance_m)} | "
        f"{_fmt_distance(r_after.min_distance_m)} |"
    )
    out.append(
        f"| Median reuse distance (m) | "
        f"{_fmt_distance(r_before.median_distance_m)} | "
        f"{_fmt_distance(r_after.median_distance_m)} |"
    )
    out.append(
        f"| p10 reuse distance (m) | "
        f"{_fmt_distance(r_before.p10_distance_m)} | "
        f"{_fmt_distance(r_after.p10_distance_m)} |"
    )
    out.append("")
    return out


def _fmt_distance(value: float | None) -> str:
    if value is None:
        return "—"
    return f"{value:.0f}"


def _render_changes(
    report: HoValidationReport,
    recommendations: list[dict[str, Any]] | None,
) -> list[str]:
    out: list[str] = []
    out.append("### Changes")
    out.append("")
    out.append(
        f"Total recommendations: **{report.n_recommendations}** "
        f"({report.churn_pct:.2f}% of {report.n_cells} cells)"
    )
    out.append("")

    if not recommendations:
        return out

    by_reason: dict[str, int] = {}
    for r in recommendations:
        by_reason[r["reason_code"]] = by_reason.get(r["reason_code"], 0) + 1
    if by_reason:
        out.append("By reason:")
        out.append("")
        out.append("| Reason | Count |")
        out.append("|---|---|")
        for reason in sorted(by_reason.keys()):
            out.append(f"| {reason} | {by_reason[reason]} |")
        out.append("")

    sorted_recs = sorted(
        recommendations,
        key=lambda r: -float(r.get("predicted_ho_failures_avoided_per_period", 0.0)),
    )
    if sorted_recs:
        out.append("Top changes by predicted HO impact:")
        out.append("")
        out.append("| Cell | PCI old → new | Reason | HO avoided / wk |")
        out.append("|---|---|---|---|")
        for rec in sorted_recs[:5]:
            out.append(
                f"| `{rec['cell_id']}` | {rec['pci_old']} → {rec['pci_new']} | "
                f"{rec['reason_code']} | "
                f"~{float(rec.get('predicted_ho_failures_avoided_per_period', 0)):.0f} |"
            )
        out.append("")

    return out
