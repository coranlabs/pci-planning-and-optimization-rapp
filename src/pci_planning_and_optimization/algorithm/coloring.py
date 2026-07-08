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
from dataclasses import asdict, dataclass, field
from datetime import UTC, datetime

from pci_planning_and_optimization.algorithm.conflict_graph import (
    AllConflicts,
    all_conflicts,
)
from pci_planning_and_optimization.algorithm.scoring import (
    WeightProvider,
    candidate_sort_key,
    compute_total_soft_cost,
)
from pci_planning_and_optimization.app_config import AppConfig
from pci_planning_and_optimization.models import Cell, Network, Technology
from pci_planning_and_optimization.weighting.policy import OperatorPolicy

_log = logging.getLogger(__name__)


REASON_COLLISION = "PCI_COLLISION_RESOLUTION"
REASON_CONFUSION = "PCI_CONFUSION_RESOLUTION"
REASON_MODN = "MODN_INTERFERENCE_REDUCTION"


def default_weight_provider(network: Network) -> WeightProvider:
    from pci_planning_and_optimization.weighting.distance import EuclideanDistanceProvider
    from pci_planning_and_optimization.weighting.handover import HoFailureRateProvider
    from pci_planning_and_optimization.weighting.handover_fallback import (
        CellLevelHoFallback,
    )

    if any(r.ho_failures for r in network.relations):
        return HoFailureRateProvider(network=network)

    has_pair_attempts = any(r.ho_attempts for r in network.relations)
    has_cell_totals = any(c.ho_attempts_total for c in network.cells.values())
    if has_pair_attempts and has_cell_totals:
        _log.info(
            "per-pair HO failure counters absent — inferring edge weights from "
            "cell-level totals by proportional attribution"
        )
        return CellLevelHoFallback(network=network)

    _log.info(
        "no HO counters in this network — weighting edges by distance/RF "
        "overlap instead (mod-N ordering and the revert guard need a "
        "non-zero weight to function)"
    )
    return EuclideanDistanceProvider()


@dataclass
class ChangeRecommendation:

    cell_id: str
    technology: str
    mo_class: str

    pci_old: int
    pci_new: int
    pci_components_new: tuple[int, int] | None

    reason_code: str
    reason_text: str

    sort_key_old: tuple[float, ...]
    sort_key_new: tuple[float, ...]

    predicted_ho_failures_avoided_per_period: float

    pass_number: int
    locked_neighborhood: list[str]

    def to_dict(self) -> dict[str, object]:
        d = asdict(self)
        d["sort_key_old"] = list(self.sort_key_old)
        d["sort_key_new"] = list(self.sort_key_new)
        if self.pci_components_new is not None:
            d["pci_components_new"] = {
                "group": self.pci_components_new[0],
                "sub": self.pci_components_new[1],
            }
        d["predicted_ho_failures_avoided_per_period"] = round(
            self.predicted_ho_failures_avoided_per_period, 1
        )
        return d


@dataclass
class PassSummary:
    pass_number: int
    n_changes: int
    soft_cost_before: float
    soft_cost_after: float
    improvement: float
    stopped_reason: str

    def to_dict(self) -> dict[str, object]:
        return {
            "pass_number": self.pass_number,
            "n_changes": self.n_changes,
            "soft_cost_before": round(self.soft_cost_before, 5),
            "soft_cost_after": round(self.soft_cost_after, 5),
            "improvement": round(self.improvement, 5),
            "stopped_reason": self.stopped_reason,
        }


@dataclass
class OptimizationRun:
    technology: str
    generated_at: str
    n_cells: int
    n_pairs_evaluated: int

    passes_executed: int
    converged: bool
    final_soft_cost: float

    changes: list[ChangeRecommendation] = field(default_factory=list)
    pass_history: list[PassSummary] = field(default_factory=list)

    config_snapshot: dict[str, object] = field(default_factory=dict)

    def to_dict(self) -> dict[str, object]:
        return {
            "technology": self.technology,
            "generated_at": self.generated_at,
            "n_cells": self.n_cells,
            "n_pairs_evaluated": self.n_pairs_evaluated,
            "passes_executed": self.passes_executed,
            "converged": self.converged,
            "final_soft_cost": round(self.final_soft_cost, 5),
            "changes": [c.to_dict() for c in self.changes],
            "pass_history": [ps.to_dict() for ps in self.pass_history],
            "config_snapshot": self.config_snapshot,
        }


def pci_usage_by_frequency(
    network: Network, technology: Technology
) -> dict[object, dict[int, int]]:
    out: dict[object, dict[int, int]] = {}
    for cell in network.cells.values():
        if cell.technology != technology:
            continue
        freq = cell.primary_frequency()
        if freq is None:
            continue
        counts = out.setdefault(freq, {})
        counts[cell.pci] = counts.get(cell.pci, 0) + 1
    return out


def pick_pci(
    cell: Cell,
    allowed_pool: set[int],
    network: Network,
    scoring_cfg,
    weight_provider: WeightProvider,
    *,
    pci_usage: dict[int, int] | None = None,
) -> tuple[int, tuple[float, ...]] | None:
    if not allowed_pool:
        return None

    neighbors = network.neighbors_of(cell.id, same_tech_only=True)

    best_pci: int | None = None
    best_key: tuple[float, ...] | None = None

    for cand in allowed_pool:
        key = candidate_sort_key(
            network, cell, cand, scoring_cfg, weight_provider,
            neighbors=neighbors, pci_usage=pci_usage,
        )
        if best_key is None or key < best_key:
            best_key = key
            best_pci = cand

    assert best_pci is not None and best_key is not None
    return best_pci, best_key


def _cells_to_consider(
    network: Network,
    technology: Technology,
    bundle: AllConflicts,
) -> list[Cell]:
    tier1_ids: set[str] = set()
    for edge in bundle.collisions:
        tier1_ids.add(edge.cell_a_id)
        tier1_ids.add(edge.cell_b_id)
    for edge in bundle.confusions:
        tier1_ids.add(edge.cell_a_id)
        tier1_ids.add(edge.cell_b_id)

    cell_ho_impact: dict[str, int] = {}
    for edge_list in (bundle.mod3, bundle.mod4, bundle.mod30, bundle.mod6):
        for edge in edge_list:
            for cid in (edge.cell_a_id, edge.cell_b_id):
                cell_ho_impact[cid] = cell_ho_impact.get(cid, 0) + edge.ho_failures

    tier2_ids = set(cell_ho_impact.keys()) - tier1_ids

    def t1_priority(cell_id: str) -> tuple[float, str]:
        cell = network.cells[cell_id]
        prb = cell.prb_util if cell.prb_util is not None else 0.0
        impact = cell_ho_impact.get(cell_id, 0)
        return (-prb * impact, cell_id)

    def t2_priority(cell_id: str) -> tuple[float, str]:
        cell = network.cells[cell_id]
        prb = cell.prb_util if cell.prb_util is not None else 0.0
        return (-prb * cell_ho_impact.get(cell_id, 0), cell_id)

    tier1_sorted = sorted(tier1_ids, key=t1_priority)
    tier2_sorted = sorted(tier2_ids, key=t2_priority)

    out: list[Cell] = []
    for cid in tier1_sorted:
        if cid in network.cells and network.cells[cid].technology == technology:
            out.append(network.cells[cid])
    for cid in tier2_sorted:
        if cid in network.cells and network.cells[cid].technology == technology:
            out.append(network.cells[cid])
    return out


def _lock_neighborhood(
    network: Network, cell_id: str, locked: set[str]
) -> list[str]:
    newly = [cell_id]
    locked.add(cell_id)
    for nid in network.n_hop_neighborhood(cell_id, n=2, same_tech_only=True):
        if nid not in locked:
            newly.append(nid)
            locked.add(nid)
    return newly


def _resolve_reason(
    cell: Cell, bundle: AllConflicts
) -> tuple[str, str]:
    cell_id = cell.id
    for edge in bundle.collisions:
        if cell_id in (edge.cell_a_id, edge.cell_b_id):
            partner = edge.cell_b_id if edge.cell_a_id == cell_id else edge.cell_a_id
            return (
                REASON_COLLISION,
                f"Hard PCI collision with {partner} on shared frequency",
            )
    for edge in bundle.confusions:
        if cell_id in (edge.cell_a_id, edge.cell_b_id):
            partner = edge.cell_b_id if edge.cell_a_id == cell_id else edge.cell_a_id
            return (
                REASON_CONFUSION,
                f"PCI confusion involving {partner}",
            )
    return (
        REASON_MODN,
        "Mod-N interference reduction with same-frequency neighbors",
    )


def _apply_pci_change(cell: Cell, new_pci: int) -> None:
    cell.pci = new_pci
    if cell.technology == Technology.LTE:
        cell.pci_components = (new_pci // 3, new_pci % 3)


def conservative_color_pass(
    network: Network,
    technology: Technology,
    config: AppConfig,
    weight_provider: WeightProvider,
    policy: OperatorPolicy,
    *,
    per_pass_budget: int,
    pass_number: int,
    locked_cells: set[str] | None = None,
) -> tuple[list[ChangeRecommendation], set[str]]:
    locked = set(locked_cells) if locked_cells else set()

    bundle = all_conflicts(
        network, technology, enable_mod6_lte=config.scoring.lte.enable_mod6
    )

    candidates = _cells_to_consider(network, technology, bundle)

    usage_by_frequency = pci_usage_by_frequency(network, technology)

    changes: list[ChangeRecommendation] = []

    for cell in candidates:
        if len(changes) >= per_pass_budget:
            _log.info(
                "[%s] pass %d: per-pass budget %d exhausted",
                technology.value, pass_number, per_pass_budget,
            )
            break
        if cell.id in locked:
            continue

        allowed = policy.allowed_pool_for(cell)
        if not allowed:
            _log.warning(
                "[%s] pass %d: pool exhausted for cell %s (cell_type=%s) — skipping",
                technology.value, pass_number, cell.id, cell.cell_type,
            )
            continue

        old_pci = cell.pci
        usage = usage_by_frequency.get(cell.primary_frequency(), {})
        old_key = candidate_sort_key(
            network, cell, old_pci, config.scoring, weight_provider, pci_usage=usage,
        )

        result = pick_pci(
            cell, allowed, network, config.scoring, weight_provider, pci_usage=usage,
        )
        if result is None:
            continue
        new_pci, new_key = result

        if new_pci == old_pci:
            continue
        if new_key >= old_key:
            continue

        soft_before = compute_total_soft_cost(
            network, technology, weight_provider, config.scoring
        )
        _apply_pci_change(cell, new_pci)
        soft_after = compute_total_soft_cost(
            network, technology, weight_provider, config.scoring
        )

        if soft_after > soft_before:
            _apply_pci_change(cell, old_pci)
            _log.info(
                "[%s] pass %d: cell %s change %d→%d would INCREASE total soft cost "
                "(%.4f → %.4f) — reverting",
                technology.value, pass_number, cell.id, old_pci, new_pci,
                soft_before, soft_after,
            )
            continue

        usage[old_pci] = max(0, usage.get(old_pci, 1) - 1)
        usage[new_pci] = usage.get(new_pci, 0) + 1

        ho_impact = _estimate_ho_avoided(network, cell, old_pci, new_pci, weight_provider)

        newly_locked = _lock_neighborhood(network, cell.id, locked)

        reason_code, reason_text = _resolve_reason(cell, bundle)

        rec = ChangeRecommendation(
            cell_id=cell.id,
            technology=cell.technology.value,
            mo_class=cell.mo_class,
            pci_old=old_pci,
            pci_new=new_pci,
            pci_components_new=(
                (new_pci // 3, new_pci % 3) if cell.technology == Technology.LTE else None
            ),
            reason_code=reason_code,
            reason_text=reason_text,
            sort_key_old=old_key,
            sort_key_new=new_key,
            predicted_ho_failures_avoided_per_period=ho_impact,
            pass_number=pass_number,
            locked_neighborhood=newly_locked,
        )
        changes.append(rec)
        _log.info(
            "[%s] pass %d: cell %s %d→%d  reason=%s  Δsoft=%.4f  +%s locked",
            technology.value, pass_number, cell.id, old_pci, new_pci,
            reason_code, soft_before - soft_after, len(newly_locked),
        )

    return changes, locked


def _estimate_ho_avoided(
    network: Network,
    cell: Cell,
    old_pci: int,
    new_pci: int,
    weight_provider: WeightProvider,
) -> float:
    neighbors = [
        n for n in network.neighbors_of(cell.id, same_tech_only=True)
        if n.primary_frequency() == cell.primary_frequency()
        and cell.primary_frequency() is not None
    ]
    avoided = 0.0
    for u in neighbors:
        fwd = network.relation(cell.id, u.id)
        rev = network.relation(u.id, cell.id)
        fails = (fwd.ho_failures if fwd else 0) + (rev.ho_failures if rev else 0)
        if fails == 0:
            continue

        if old_pci == u.pci and new_pci != u.pci:
            avoided += 1.0 * fails
            continue
        if (old_pci % 3) == (u.pci % 3) and (new_pci % 3) != (u.pci % 3):
            avoided += 0.4 * fails
        if cell.technology == Technology.NR and (old_pci % 4) == (u.pci % 4) and (new_pci % 4) != (u.pci % 4):
            avoided += 0.3 * fails
        if (old_pci % 30) == (u.pci % 30) and (new_pci % 30) != (u.pci % 30):
            avoided += 0.3 * fails
    return avoided


def _budget_cells(network: Network, technology: Technology, pct: float) -> int:
    n = sum(1 for c in network.cells.values() if c.technology == technology)
    return max(1, int(round(n * pct)))


def run_optimization(
    network: Network,
    technology: Technology,
    config: AppConfig,
    *,
    weight_provider: WeightProvider | None = None,
    policy: OperatorPolicy | None = None,
    max_changes_override: int | None = None,
) -> OptimizationRun:
    weight_provider = weight_provider or default_weight_provider(network)
    policy = policy or OperatorPolicy(config)
    policy.validate_pool_sizes(network)

    if max_changes_override is not None:
        per_run_budget = max_changes_override
    else:
        per_run_budget = _budget_cells(
            network, technology, config.convergence.per_run_budget_pct
        )
    per_run_budget = min(per_run_budget, config.convergence.max_absolute_changes)

    per_pass_budget = _budget_cells(
        network, technology, config.convergence.per_pass_budget_pct
    )
    if max_changes_override is not None:
        needed = max(1, (per_run_budget + config.convergence.max_passes - 1) // config.convergence.max_passes)
        per_pass_budget = max(per_pass_budget, needed)

    all_changes: list[ChangeRecommendation] = []
    pass_history: list[PassSummary] = []
    n_cells = sum(1 for c in network.cells.values() if c.technology == technology)
    last_total = compute_total_soft_cost(
        network, technology, weight_provider, config.scoring
    )

    converged = False
    passes_executed = 0

    for pass_idx in range(config.convergence.max_passes):
        passes_executed = pass_idx + 1

        if len(all_changes) >= per_run_budget:
            pass_history.append(PassSummary(
                pass_number=passes_executed,
                n_changes=0,
                soft_cost_before=last_total,
                soft_cost_after=last_total,
                improvement=0.0,
                stopped_reason="run_budget_exhausted",
            ))
            _log.info(
                "[%s] run budget %d exhausted before pass %d",
                technology.value, per_run_budget, passes_executed,
            )
            break

        remaining_budget = per_run_budget - len(all_changes)
        budget_this_pass = min(per_pass_budget, remaining_budget)

        soft_before = compute_total_soft_cost(
            network, technology, weight_provider, config.scoring
        )

        changes, _locked = conservative_color_pass(
            network, technology, config, weight_provider, policy,
            per_pass_budget=budget_this_pass,
            pass_number=passes_executed,
            locked_cells=None,
        )
        all_changes.extend(changes)

        soft_after = compute_total_soft_cost(
            network, technology, weight_provider, config.scoring
        )
        improvement = soft_before - soft_after

        if not changes:
            pass_history.append(PassSummary(
                pass_number=passes_executed,
                n_changes=0,
                soft_cost_before=soft_before,
                soft_cost_after=soft_after,
                improvement=improvement,
                stopped_reason="converged_no_changes",
            ))
            converged = True
            _log.info(
                "[%s] pass %d: no changes — CONVERGED",
                technology.value, passes_executed,
            )
            break

        if improvement < config.convergence.min_soft_cost_improvement:
            pass_history.append(PassSummary(
                pass_number=passes_executed,
                n_changes=len(changes),
                soft_cost_before=soft_before,
                soft_cost_after=soft_after,
                improvement=improvement,
                stopped_reason="insufficient_improvement",
            ))
            _log.info(
                "[%s] pass %d: improvement %.5f < %.5f — STOPPING (oscillation guard)",
                technology.value, passes_executed,
                improvement, config.convergence.min_soft_cost_improvement,
            )
            break

        pass_history.append(PassSummary(
            pass_number=passes_executed,
            n_changes=len(changes),
            soft_cost_before=soft_before,
            soft_cost_after=soft_after,
            improvement=improvement,
            stopped_reason="continuing",
        ))
        last_total = soft_after
    else:
        _log.info(
            "[%s] max_passes %d reached",
            technology.value, config.convergence.max_passes,
        )

    final_total = compute_total_soft_cost(
        network, technology, weight_provider, config.scoring
    )

    n_pairs = 0
    seen: set[tuple[str, str]] = set()
    for r in network.relations:
        if r.cross_technology:
            continue
        a = network.cells.get(r.source_cell_id)
        b = network.cells.get(r.target_cell_id)
        if a is None or b is None:
            continue
        if a.technology != technology or b.technology != technology:
            continue
        x_id, y_id = (a.id, b.id) if a.id < b.id else (b.id, a.id)
        if (x_id, y_id) in seen:
            continue
        seen.add((x_id, y_id))
        n_pairs += 1

    return OptimizationRun(
        technology=technology.value,
        generated_at=datetime.now(UTC).isoformat(timespec="seconds"),
        n_cells=n_cells,
        n_pairs_evaluated=n_pairs,
        passes_executed=passes_executed,
        converged=converged,
        final_soft_cost=final_total,
        changes=all_changes,
        pass_history=pass_history,
        config_snapshot={
            "max_passes": config.convergence.max_passes,
            "per_pass_budget_pct": config.convergence.per_pass_budget_pct,
            "per_run_budget_pct": config.convergence.per_run_budget_pct,
            "max_absolute_changes": config.convergence.max_absolute_changes,
            "per_run_budget_used": per_run_budget,
            "min_soft_cost_improvement": config.convergence.min_soft_cost_improvement,
            "scoring_lte_mod_priority": config.scoring.lte.mod_priority,
            "scoring_lte_enable_mod6": config.scoring.lte.enable_mod6,
            "scoring_nr_mod_priority": config.scoring.nr.mod_priority,
        },
    )
