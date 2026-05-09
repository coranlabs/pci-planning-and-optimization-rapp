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

import json
import logging
import sys
from pathlib import Path

import click

from pci_planning_and_optimization import __version__, banner
from pci_planning_and_optimization.algorithm.conflict_graph import (
    CLASS_COLLISION,
    CLASS_CONFUSION,
    CLASS_MOD3,
    CLASS_MOD4,
    CLASS_MOD30,
)
from pci_planning_and_optimization.app_config import AppConfig, load_config, unfilled
from pci_planning_and_optimization.logging_setup import (
    LOG_FORMAT_ENV,
    setup_logging,
    with_tech,
)

_DEFAULT_CONFIG_PATH = "config/config.yaml"


@click.group(context_settings={"help_option_names": ["-h", "--help"]})
@click.version_option(__version__, prog_name="pci-planning-and-optimization")
@click.option(
    "--config", "config_path",
    default=_DEFAULT_CONFIG_PATH, show_default=True,
    type=click.Path(),
    help="Path to YAML config file.",
)
@click.option(
    "--technology",
    type=click.Choice(["lte", "nr", "all"]),
    default="all", show_default=True,
    help="Which technology to operate on. Subcommands respect this filter.",
)
@click.option(
    "--pm-dir",
    default=None, type=click.Path(),
    help=(
        "Directory of 3GPP TS 32.435 PM XML to read the network from. "
        "Overrides osc.pm_directory / PM_DIRECTORY."
    ),
)
@click.option(
    "--log-level",
    type=click.Choice(["DEBUG", "INFO", "WARNING", "ERROR"]),
    default="INFO", show_default=True,
    help="Logging verbosity.",
)
@click.pass_context
def cli(
    ctx: click.Context,
    config_path: str,
    technology: str,
    pm_dir: str | None,
    log_level: str,
) -> None:
    setup_logging(level=log_level)
    asking_for_help = {"-h", "--help"} & set(sys.argv)
    if ctx.invoked_subcommand not in (None, "serve") and not asking_for_help:
        banner.command(
            "PCI", "pci-planning-and-optimization", __version__,
            ctx.invoked_subcommand,
        )
    ctx.ensure_object(dict)
    ctx.obj["config_path"] = config_path
    ctx.obj["technology"] = technology
    ctx.obj["pm_dir"] = pm_dir
    ctx.obj["log_level"] = log_level


def _load_cfg(ctx: click.Context) -> AppConfig:
    if "cfg" not in ctx.obj:
        ctx.obj["cfg"] = load_config(ctx.obj["config_path"])
    return ctx.obj["cfg"]


def _pm_dir(ctx: click.Context) -> str:
    pm_dir = ctx.obj.get("pm_dir") or _load_cfg(ctx).osc.pm_directory
    if not pm_dir:
        raise click.UsageError(
            "no PM directory: pass --pm-dir, set osc.pm_directory in the "
            "config, or export PM_DIRECTORY."
        )
    return str(pm_dir)


def _load_network(ctx: click.Context):
    from pci_planning_and_optimization.osc.ingest import load_network_from_directory

    pm_dir = _pm_dir(ctx)
    logging.getLogger("pci_planning_and_optimization.osc").info(
        "PM ingest from %s", pm_dir
    )
    return load_network_from_directory(
        pm_dir, max_files=_load_cfg(ctx).osc.max_files_per_refresh
    )


@cli.command()
@click.option(
    "--output", "output_file",
    type=click.Path(dir_okay=False),
    default="runs/correlation.json", show_default=True,
    help="Path to write the correlation report (JSON).",
)
@click.pass_context
def hypothesis(ctx: click.Context, output_file: str) -> None:
    from pci_planning_and_optimization.correlation import compute_ho_correlation
    from pci_planning_and_optimization.models import Technology

    cfg = _load_cfg(ctx)
    technology_filter = ctx.obj["technology"]
    log = logging.getLogger("pci_planning_and_optimization.hypothesis")

    network = _load_network(ctx)

    techs_to_run: list[Technology]
    if technology_filter == "all":
        techs_to_run = [Technology.LTE, Technology.NR]
    elif technology_filter == "lte":
        techs_to_run = [Technology.LTE]
    else:
        techs_to_run = [Technology.NR]

    payload: dict[str, object] = {
        "input": _pm_dir(ctx),
        "config": ctx.obj["config_path"],
        "technology_filter": technology_filter,
        "results": {},
    }
    any_ship = False
    any_run = False

    for tech in techs_to_run:
        tech_log = with_tech(log, tech.value)
        tech_log.info("running hypothesis gate")

        lte_net, nr_net = network.split_by_technology()
        sub = lte_net if tech == Technology.LTE else nr_net
        if not sub.cells:
            tech_log.warning("no cells of this technology — skipping")
            payload["results"][tech.value] = {
                "skipped": True,
                "reason": f"No cells of technology={tech.value} in input",
            }
            continue

        report = compute_ho_correlation(
            sub,
            tech,
            min_correlation_ratio=cfg.hypothesis.min_correlation_ratio,
        )
        any_run = True
        any_ship = any_ship or report.gate_passed

        tech_log.info(
            "verdict=%s ratio=%s p_value=%s pairs_total=%d below_threshold=%d",
            report.verdict,
            f"{report.ratio:.3f}" if report.ratio is not None else "n/a",
            f"{report.p_value:.4f}" if report.p_value is not None else "n/a",
            report.n_pairs_total,
            report.n_pairs_below_attempt_threshold,
        )

        payload["results"][tech.value] = report.to_dict()

        click.echo(
            f"[{tech.value.upper()}] {report.verdict}  "
            f"ratio={report.ratio:.3f}× "
            f"any_conflict={report.any_conflict_failure_rate:.3f} "
            f"clean={report.clean_failure_rate:.3f} "
            f"p={report.p_value:.4f} "
            f"pairs={report.n_pairs_total - report.n_pairs_below_attempt_threshold}"
            if report.ratio is not None and report.p_value is not None
            else f"[{tech.value.upper()}] {report.verdict}  (insufficient samples)"
        )
        click.echo(f"          reason: {report.reason}")

    out_path = Path(output_file)
    out_path.parent.mkdir(parents=True, exist_ok=True)
    with out_path.open("w", encoding="utf-8") as f:
        json.dump(payload, f, indent=2, sort_keys=False)
        f.write("\n")
    log.info("wrote %s", out_path)

    if not any_run:
        sys.exit(2)
    sys.exit(0 if any_ship else 1)


@cli.command()
@click.option(
    "--output", "output_file",
    type=click.Path(dir_okay=False),
    default="runs/conflicts.json", show_default=True,
)
@click.option(
    "--top-n",
    type=int, default=20, show_default=True,
    help="How many highest-HO-impact real conflicts to surface in `top_impact`.",
)
@click.pass_context
def detect(
    ctx: click.Context,
    output_file: str,
    top_n: int,
) -> None:
    from pci_planning_and_optimization.algorithm.conflict_graph import prepare_network
    from pci_planning_and_optimization.algorithm.report import generate_conflict_report
    from pci_planning_and_optimization.models import Technology

    cfg = _load_cfg(ctx)
    technology_filter = ctx.obj["technology"]
    log = logging.getLogger("pci_planning_and_optimization.detect")

    network = _load_network(ctx)
    n_total_cells = len(network.cells)
    log.info("loaded %d cells, %d directed relations", n_total_cells, len(network.relations))

    prepare_network(network, cfg)

    techs_to_run: list[Technology]
    if technology_filter == "all":
        techs_to_run = [Technology.LTE, Technology.NR]
    elif technology_filter == "lte":
        techs_to_run = [Technology.LTE]
    else:
        techs_to_run = [Technology.NR]

    payload: dict[str, object] = {
        "input": _pm_dir(ctx),
        "config": ctx.obj["config_path"],
        "technology_filter": technology_filter,
        "results": {},
    }
    any_run = False
    any_conflicts_found = False

    for tech in techs_to_run:
        tech_log = with_tech(log, tech.value)
        n_cells_in_tech = sum(
            1 for c in network.cells.values() if c.technology == tech
        )
        if n_cells_in_tech == 0:
            tech_log.warning("no cells of this technology — skipping")
            payload["results"][tech.value] = {
                "skipped": True,
                "reason": f"No cells of technology={tech.value} in input",
            }
            continue

        enable_mod6 = (
            cfg.scoring.lte.enable_mod6 if tech == Technology.LTE else False
        )
        report = generate_conflict_report(
            network, tech, enable_mod6_lte=enable_mod6, top_n=top_n,
        )
        any_run = True
        if report.n_pairs_total > 0:
            any_conflicts_found = True

        cs = report.class_summary
        tech_log.info(
            "n_cells=%d n_pairs=%d real=%d shadow=%d  "
            "collisions=%d confusions=%d mod3=%d mod4=%d mod30=%d",
            report.n_cells, report.n_pairs_total,
            report.n_pairs_real, report.n_pairs_shadow,
            cs[CLASS_COLLISION].n_pairs, cs[CLASS_CONFUSION].n_pairs,
            cs[CLASS_MOD3].n_pairs, cs[CLASS_MOD4].n_pairs, cs[CLASS_MOD30].n_pairs,
        )

        payload["results"][tech.value] = report.to_dict()

        click.echo(
            f"[{tech.value.upper()}] cells={report.n_cells}  "
            f"conflicts={report.n_pairs_total} (real={report.n_pairs_real}, shadow={report.n_pairs_shadow})  "
            f"collisions={cs[CLASS_COLLISION].n_pairs}  "
            f"confusions={cs[CLASS_CONFUSION].n_pairs}  "
            f"mod3={cs[CLASS_MOD3].n_pairs}  "
            f"mod4={cs[CLASS_MOD4].n_pairs}  "
            f"mod30={cs[CLASS_MOD30].n_pairs}  "
            f"predicted_ho_avoided≈{report.predicted_ho_failures_avoided:.0f}/wk"
        )

    out_path = Path(output_file)
    out_path.parent.mkdir(parents=True, exist_ok=True)
    with out_path.open("w", encoding="utf-8") as f:
        json.dump(payload, f, indent=2, sort_keys=False)
        f.write("\n")
    log.info("wrote %s", out_path)

    if not any_run:
        sys.exit(2)
    _ = any_conflicts_found
    sys.exit(0)


