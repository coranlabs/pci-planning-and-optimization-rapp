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

from dataclasses import asdict, dataclass, field
from datetime import UTC, datetime

from scipy.stats import mannwhitneyu

from pci_planning_and_optimization.models import Cell, Network, RelationSource, Technology

DEFAULT_MIN_PAIR_ATTEMPTS = 30

DEFAULT_MIN_POOL_SIZE = 5

DEFAULT_P_VALUE_THRESHOLD = 0.05

CLASS_COLLISION = "collision"
CLASS_CONFUSION = "confusion"
CLASS_MOD3_ONLY = "mod3_only"
CLASS_MOD4_ONLY = "mod4_only"
CLASS_MOD30_ONLY = "mod30_only"
CLASS_MULTI_MOD = "multi_mod"
CLASS_CLEAN = "clean"

VERDICT_SHIP = "SHIP"
VERDICT_DO_NOT_SHIP = "DO NOT SHIP"
VERDICT_NEEDS_MORE_DATA = "NEEDS MORE DATA"


@dataclass
class ClassStats:

    name: str
    n_pairs: int = 0
    total_attempts: int = 0
    total_failures: int = 0
    pair_failure_rates: list[float] = field(default_factory=list, repr=False)

    @property
    def weighted_failure_rate(self) -> float:
        if self.total_attempts == 0:
            return 0.0
        return self.total_failures / self.total_attempts

    @property
    def mean_pair_failure_rate(self) -> float:
        if not self.pair_failure_rates:
            return 0.0
        return sum(self.pair_failure_rates) / len(self.pair_failure_rates)

    def to_dict(self) -> dict[str, object]:
        return {
            "name": self.name,
            "n_pairs": self.n_pairs,
            "total_attempts": self.total_attempts,
            "total_failures": self.total_failures,
            "weighted_failure_rate": round(self.weighted_failure_rate, 5),
            "mean_pair_failure_rate": round(self.mean_pair_failure_rate, 5),
        }


@dataclass
class HoCorrelationReport:

    technology: str
    generated_at: str
    min_correlation_ratio: float
    min_pair_attempts: int
    min_pool_size: int
    p_value_threshold: float

    n_pairs_total: int
    n_pairs_below_attempt_threshold: int

    classes: dict[str, ClassStats]

    any_conflict_failure_rate: float
    clean_failure_rate: float
    ratio: float | None
    p_value: float | None

    gate_passed: bool
    verdict: str
    reason: str

    def to_dict(self) -> dict[str, object]:
        d = asdict(self)
        d["classes"] = {name: cs.to_dict() for name, cs in self.classes.items()}
        if d["any_conflict_failure_rate"] is not None:
            d["any_conflict_failure_rate"] = round(d["any_conflict_failure_rate"], 5)
        if d["clean_failure_rate"] is not None:
            d["clean_failure_rate"] = round(d["clean_failure_rate"], 5)
        if d["ratio"] is not None:
            d["ratio"] = round(d["ratio"], 4)
        if d["p_value"] is not None:
            d["p_value"] = round(d["p_value"], 6)
        return d


def _real_neighbor_ids(network: Network, cell_id: str) -> set:
    out: set = set()
    for r in network.relations:
        if r.relation_source != RelationSource.REAL:
            continue
        if r.source_cell_id == cell_id:
            out.add(r.target_cell_id)
        elif r.target_cell_id == cell_id:
            out.add(r.source_cell_id)
    return out


def _is_confusion_pair(network: Network, a: Cell, b: Cell) -> bool:
    for source, target in ((a, b), (b, a)):
        for nb_id in _real_neighbor_ids(network, source.id):
            if nb_id == target.id:
                continue
            nb = network.cells.get(nb_id)
            if nb is None or nb.technology != source.technology:
                continue
            if nb.pci != target.pci:
                continue
            if nb.primary_frequency() != target.primary_frequency():
                continue
            return True
    return False


def _classify_pair(
    network: Network,
    a: Cell,
    b: Cell,
    *,
    is_nr: bool,
) -> str:
    if network.is_pci_conflict(a.id, b.id):
        return CLASS_COLLISION

    if _is_confusion_pair(network, a, b):
        return CLASS_CONFUSION

    if a.primary_frequency() != b.primary_frequency():
        return CLASS_CLEAN

    matches: list[int] = []
    if (a.pci % 3) == (b.pci % 3):
        matches.append(3)
    if is_nr and (a.pci % 4) == (b.pci % 4):
        matches.append(4)
    if (a.pci % 30) == (b.pci % 30):
        matches.append(30)

    if len(matches) == 0:
        return CLASS_CLEAN
    if len(matches) > 1:
        return CLASS_MULTI_MOD
    n = matches[0]
    if n == 3:
        return CLASS_MOD3_ONLY
    if n == 4:
        return CLASS_MOD4_ONLY
    if n == 30:
        return CLASS_MOD30_ONLY
    return CLASS_CLEAN


def _unique_intra_tech_pairs(
    network: Network, technology: Technology
) -> list[tuple[Cell, Cell]]:
    seen: set[frozenset[str]] = set()
    pairs: list[tuple[Cell, Cell]] = []
    for r in network.relations:
        if r.relation_source != RelationSource.REAL:
            continue
        if r.cross_technology:
            continue
        a = network.cells.get(r.source_cell_id)
        b = network.cells.get(r.target_cell_id)
        if a is None or b is None:
            continue
        if a.technology != technology or b.technology != technology:
            continue
        if a.id == b.id:
            continue
        x, y = (a, b) if a.id < b.id else (b, a)
        key = frozenset({x.id, y.id})
        if key in seen:
            continue
        seen.add(key)
        pairs.append((x, y))
    return pairs


def compute_ho_correlation(
    network: Network,
    technology: Technology,
    *,
    min_correlation_ratio: float = 2.0,
    min_pair_attempts: int = DEFAULT_MIN_PAIR_ATTEMPTS,
    min_pool_size: int = DEFAULT_MIN_POOL_SIZE,
    p_value_threshold: float = DEFAULT_P_VALUE_THRESHOLD,
) -> HoCorrelationReport:
    is_nr = technology == Technology.NR

    classes: dict[str, ClassStats] = {
        CLASS_COLLISION: ClassStats(name=CLASS_COLLISION),
        CLASS_CONFUSION: ClassStats(name=CLASS_CONFUSION),
        CLASS_MOD3_ONLY: ClassStats(name=CLASS_MOD3_ONLY),
        CLASS_MOD4_ONLY: ClassStats(name=CLASS_MOD4_ONLY),
        CLASS_MOD30_ONLY: ClassStats(name=CLASS_MOD30_ONLY),
        CLASS_MULTI_MOD: ClassStats(name=CLASS_MULTI_MOD),
        CLASS_CLEAN: ClassStats(name=CLASS_CLEAN),
    }

    n_total = 0
    n_below_thr = 0

    pairs = _unique_intra_tech_pairs(network, technology)

    for a, b in pairs:
        n_total += 1
        attempts = network.ho_attempts_pair(a.id, b.id)
        if attempts < min_pair_attempts:
            n_below_thr += 1
            continue

        klass = _classify_pair(network, a, b, is_nr=is_nr)
        cs = classes[klass]
        cs.n_pairs += 1
        cs.total_attempts += attempts

        fwd = network.relation(a.id, b.id)
        rev = network.relation(b.id, a.id)
        fails = (fwd.ho_failures if fwd else 0) + (rev.ho_failures if rev else 0)
        cs.total_failures += fails
        cs.pair_failure_rates.append(fails / attempts if attempts else 0.0)

    conflict_keys = (
        CLASS_COLLISION, CLASS_CONFUSION,
        CLASS_MOD3_ONLY, CLASS_MOD4_ONLY, CLASS_MOD30_ONLY, CLASS_MULTI_MOD,
    )
    conflict_attempts = sum(classes[k].total_attempts for k in conflict_keys)
    conflict_failures = sum(classes[k].total_failures for k in conflict_keys)
    conflict_rates: list[float] = []
    for k in conflict_keys:
        conflict_rates.extend(classes[k].pair_failure_rates)

    clean_attempts = classes[CLASS_CLEAN].total_attempts
    clean_failures = classes[CLASS_CLEAN].total_failures
    clean_rates = list(classes[CLASS_CLEAN].pair_failure_rates)

    any_conflict_rate = (
        conflict_failures / conflict_attempts if conflict_attempts else 0.0
    )
    clean_rate = clean_failures / clean_attempts if clean_attempts else 0.0
    ratio: float | None
    if clean_rate > 0:
        ratio = any_conflict_rate / clean_rate
    else:
        ratio = None

    p_value: float | None
    if len(conflict_rates) >= 2 and len(clean_rates) >= 2:
        try:
            _, p = mannwhitneyu(
                conflict_rates, clean_rates, alternative="greater"
            )
            p_value = float(p)
        except ValueError:
            p_value = None
    else:
        p_value = None

    enough_samples = (
        len(conflict_rates) >= min_pool_size
        and len(clean_rates) >= min_pool_size
    )

    if not enough_samples:
        verdict = VERDICT_NEEDS_MORE_DATA
        reason = (
            f"Sample size too small: any_conflict={len(conflict_rates)} pairs, "
            f"clean={len(clean_rates)} pairs (need ≥ {min_pool_size} each "
            f"with ≥ {min_pair_attempts} attempts)."
        )
        gate_passed = False
    elif ratio is None:
        verdict = VERDICT_NEEDS_MORE_DATA
        reason = (
            "Clean-pair failure rate is zero — cannot compute ratio. "
            "Either no conflicts exist or the network has no HO failures on clean pairs."
        )
        gate_passed = False
    elif ratio < min_correlation_ratio:
        verdict = VERDICT_DO_NOT_SHIP
        reason = (
            f"Ratio {ratio:.2f}× below threshold {min_correlation_ratio:.2f}×. "
            "PCI conflicts do NOT measurably correlate with HO failures in this "
            "network. Investigate other root causes (mobility config, RF coverage)."
        )
        gate_passed = False
    elif p_value is not None and p_value >= p_value_threshold:
        verdict = VERDICT_NEEDS_MORE_DATA
        reason = (
            f"Ratio {ratio:.2f}× meets threshold but p-value {p_value:.4f} "
            f"≥ {p_value_threshold:.2f} — correlation not statistically "
            "significant. Collect more data."
        )
        gate_passed = False
    else:
        verdict = VERDICT_SHIP
        reason = (
            f"Ratio {ratio:.2f}× ≥ threshold {min_correlation_ratio:.2f}×"
            + (f", p-value {p_value:.4f} < {p_value_threshold:.2f}." if p_value is not None
               else " (p-value not computed).")
            + " PCI conflicts correlate with HO failures — rApp can ship."
        )
        gate_passed = True

    return HoCorrelationReport(
        technology=technology.value,
        generated_at=datetime.now(UTC).isoformat(timespec="seconds"),
        min_correlation_ratio=min_correlation_ratio,
        min_pair_attempts=min_pair_attempts,
        min_pool_size=min_pool_size,
        p_value_threshold=p_value_threshold,
        n_pairs_total=n_total,
        n_pairs_below_attempt_threshold=n_below_thr,
        classes=classes,
        any_conflict_failure_rate=any_conflict_rate,
        clean_failure_rate=clean_rate,
        ratio=ratio,
        p_value=p_value,
        gate_passed=gate_passed,
        verdict=verdict,
        reason=reason,
    )
