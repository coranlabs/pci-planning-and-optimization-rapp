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


@cli.command()
@click.option(
    "--output", "output_file",
    type=click.Path(dir_okay=False),
    default="runs/recommendations.json", show_default=True,
)
@click.option(
    "--max-changes",
    type=int, default=None,
    help="Override per-run change budget (default from config.convergence).",
)
@click.pass_context
def optimize(
    ctx: click.Context,
    output_file: str,
    max_changes: int | None,
) -> None:
    from pci_planning_and_optimization.algorithm.coloring import run_optimization
    from pci_planning_and_optimization.algorithm.conflict_graph import prepare_network
    from pci_planning_and_optimization.models import Technology

    cfg = _load_cfg(ctx)
    technology_filter = ctx.obj["technology"]
    log = logging.getLogger("pci_planning_and_optimization.optimize")

    network = _load_network(ctx)
    log.info("loaded %d cells, %d directed relations", len(network.cells), len(network.relations))

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
        "max_changes_override": max_changes,
        "results": {},
    }
    any_run = False

    for tech in techs_to_run:
        tech_log = with_tech(log, tech.value)
        n_cells_tech = sum(
            1 for c in network.cells.values() if c.technology == tech
        )
        if n_cells_tech == 0:
            tech_log.warning("no cells of this technology — skipping")
            payload["results"][tech.value] = {
                "skipped": True,
                "reason": f"No cells of technology={tech.value} in input",
            }
            continue

        run = run_optimization(
            network, tech, cfg, max_changes_override=max_changes,
        )
        any_run = True

        n_collisions = sum(
            1 for c in run.changes if c.reason_code == "PCI_COLLISION_RESOLUTION"
        )
        n_confusions = sum(
            1 for c in run.changes if c.reason_code == "PCI_CONFUSION_RESOLUTION"
        )
        n_modn = sum(
            1 for c in run.changes if c.reason_code == "MODN_INTERFERENCE_REDUCTION"
        )
        total_predicted = sum(
            c.predicted_ho_failures_avoided_per_week for c in run.changes
        )
        click.echo(
            f"[{tech.value.upper()}] cells={run.n_cells}  "
            f"changes={len(run.changes)} "
            f"(collision={n_collisions}, confusion={n_confusions}, modN={n_modn})  "
            f"passes={run.passes_executed} "
            f"converged={run.converged}  "
            f"final_soft_cost={run.final_soft_cost:.3f}  "
            f"predicted_ho_avoided≈{total_predicted:.0f}/wk"
        )

        tech_log.info(
            "completed: %d changes across %d passes (converged=%s, final_soft_cost=%.3f)",
            len(run.changes), run.passes_executed,
            run.converged, run.final_soft_cost,
        )

        payload["results"][tech.value] = run.to_dict()

    out_path = Path(output_file)
    out_path.parent.mkdir(parents=True, exist_ok=True)
    with out_path.open("w", encoding="utf-8") as f:
        json.dump(payload, f, indent=2, sort_keys=False)
        f.write("\n")
    log.info("wrote %s", out_path)

    if not any_run:
        sys.exit(2)
    sys.exit(0)


@cli.command()
@click.option(
    "--recommendations", "rec_file",
    type=click.Path(exists=True, dir_okay=False),
    required=True,
)
@click.option(
    "--output", "output_file",
    type=click.Path(dir_okay=False),
    default="runs/dashboard.md", show_default=True,
)
@click.pass_context
def validate(
    ctx: click.Context,
    rec_file: str,
    output_file: str,
) -> None:
    from pci_planning_and_optimization.algorithm.conflict_graph import prepare_network
    from pci_planning_and_optimization.models import Technology
    from pci_planning_and_optimization.validation.ho_metrics import compute_ho_validation
    from pci_planning_and_optimization.validation.reporter import render_dashboard_markdown

    cfg = _load_cfg(ctx)
    technology_filter = ctx.obj["technology"]
    log = logging.getLogger("pci_planning_and_optimization.validate")

    network = _load_network(ctx)
    log.info(
        "loaded before network: %d cells, %d directed relations",
        len(network.cells), len(network.relations),
    )
    prepare_network(network, cfg)

    with open(rec_file, encoding="utf-8") as f:
        recs_payload = json.load(f)
    log.info("loaded recommendations from %s", rec_file)

    techs_to_run: list[Technology]
    if technology_filter == "all":
        techs_to_run = [Technology.LTE, Technology.NR]
    elif technology_filter == "lte":
        techs_to_run = [Technology.LTE]
    else:
        techs_to_run = [Technology.NR]

    reports: dict[str, object] = {}
    recs_by_tech: dict[str, list[dict[str, object]]] = {}

    for tech in techs_to_run:
        tech_log = with_tech(log, tech.value)
        block = (recs_payload.get("results") or {}).get(tech.value, {})
        if isinstance(block, dict) and block.get("skipped"):
            tech_log.info("technology marked skipped in recommendations: %s", block.get("reason"))
            report = compute_ho_validation(
                network, tech,
                recommendations=[],
                skipped=True,
                skip_reason=block.get("reason", "skipped"),
                enable_mod6_lte=(
                    cfg.scoring.lte.enable_mod6 if tech == Technology.LTE else False
                ),
            )
        else:
            tech_recs = list(block.get("changes", []))
            recs_by_tech[tech.value] = tech_recs
            report = compute_ho_validation(
                network, tech,
                recommendations=tech_recs,
                enable_mod6_lte=(
                    cfg.scoring.lte.enable_mod6 if tech == Technology.LTE else False
                ),
            )
        reports[tech.value] = report

        b, a = report.before, report.after
        click.echo(
            f"[{tech.value.upper()}] cells={report.n_cells} "
            f"recs={report.n_recommendations} ({report.churn_pct:.2f}%) "
            f"collisions={b.n_collisions}->{a.n_collisions} "
            f"confusions={b.n_confusions}->{a.n_confusions} "
            f"mod3={b.n_mod3}->{a.n_mod3} "
            f"mod30={b.n_mod30}->{a.n_mod30} "
            f"predicted_ho_avoided≈{report.predicted_ho_failures_avoided_per_week:.0f}/wk"
        )

    md = render_dashboard_markdown(
        {tech: reports[tech] for tech in reports},
        recommendations_by_tech=recs_by_tech if recs_by_tech else None,
    )

    out_path = Path(output_file)
    out_path.parent.mkdir(parents=True, exist_ok=True)
    out_path.write_text(md, encoding="utf-8")
    log.info("wrote %s (%d bytes)", out_path, len(md))

    sys.exit(0)


@cli.command()
@click.option(
    "--host",
    default="0.0.0.0", show_default=True,
    help="Host interface to bind. 127.0.0.1 for local-only.",
)
@click.option(
    "--port",
    default=8080, show_default=True, type=int,
    help=(
        "TCP port for the combined dashboard, probes and /metrics. The "
        "orchestrator merges the rApp's FastAPI app with /healthz, "
        "/readyz, /startupz and /metrics on this single port."
    ),
)
@click.option(
    "--ui-dir",
    default=None, type=click.Path(),
    help="Override the dashboard asset directory. Defaults to the bundled webui.",
)
@click.option(
    "--runs-dir",
    default=None, type=click.Path(),
    help="Override OptimizationRun persistence directory. Defaults to <repo>/runs.",
)
@click.pass_context
def serve(
    ctx: click.Context,
    host: str,
    port: int,
    ui_dir: str | None,
    runs_dir: str | None,
) -> None:
    import asyncio
    import os
    import platform
    import time
    from pathlib import Path as _Path

    from pci_planning_and_optimization import banner
    from pci_planning_and_optimization.api.auth import admin_credential

    log_level = ctx.obj.get("log_level", "INFO")
    log_format = os.environ.get(LOG_FORMAT_ENV, "json").strip().lower()

    banner.title(
        "PCI Planning and Optimization",
        __version__,
        "O-RAN Non-RT-RIC rApp",
        "Conservative Graph Coloring · LTE + 5G NR",
    )

    boot_started = time.monotonic()
    banner.rule("BOOT")

    from pci_planning_and_optimization.api import server as _server_module
    from pci_planning_and_optimization.main import Orchestrator

    fastapi_app = _server_module.create_app(
        ui_dir=_Path(ui_dir) if ui_dir else None,
        runs_dir=_Path(runs_dir) if runs_dir else None,
        config_path=_Path(ctx.obj["config_path"]) if ctx.obj.get("config_path") else None,
    )

    def _influx_live() -> bool:
        writer = getattr(fastapi_app.state, "influx_writer", None)
        return bool(writer and writer.stats().get("enabled"))

    def _kafka_ingest(cfg: AppConfig | None) -> bool:
        return bool(cfg and not cfg.osc.pm_directory and cfg.osc.kafka.brokers)

    def _print_boot() -> None:
        state = fastapi_app.state
        cfg: AppConfig | None = getattr(state, "config", None)
        colour = "yes" if sys.stdout.isatty() else "off (not a tty)"

        banner.check(
            True, "runtime",
            f"python {platform.python_version()} · pid {os.getpid()} · "
            f"{platform.system().lower()}-{platform.machine()}",
        )
        if cfg is None:
            banner.check(False, "config", f"{state.config_path} · {state.config_error}")
        else:
            banner.check(
                True, "config",
                f"{state.config_path} · {len(type(cfg).model_fields)} sections · schema ok",
            )
            gaps = unfilled(cfg)
            if gaps:
                banner.check(
                    False, "unconfigured",
                    f"{state.config_path} needs to be configured · "
                    f"{len(gaps)} value(s) still to be filled",
                )
                for gap in gaps:
                    banner.check(False, "", gap)
        banner.check(
            True, "log level", f"{log_level} · format {log_format} · colour {colour}",
        )
        banner.check(True, "tracing", "in-process tracer · contextvar propagation")
        banner.check(
            True, "metrics", "prometheus registry · process_* python_* collectors",
        )
        banner.check(True, "probes", "/healthz  /readyz  /startupz  /metrics")
        banner.check(
            True, "middleware", "panic recovery · CORS · no-cache for UI assets",
        )

        operator, _ = admin_credential()
        if operator:
            banner.check(True, "auth", f"operator account '{operator}' configured")
        else:
            banner.check(
                False, "auth",
                "no operator account — set RAPP_ADMIN_USERNAME/RAPP_ADMIN_PASSWORD",
            )

        if cfg is None:
            banner.check(False, "pm ingest", "config did not load — no data source")
        elif cfg.osc.pm_directory:
            banner.check(
                True, "pm ingest",
                f"3GPP TS 32.435 PM XML from {cfg.osc.pm_directory}",
            )
        elif cfg.osc.kafka.brokers:
            banner.check(True, "pm ingest", f"topic {cfg.osc.kafka.topic}")
            banner.check(
                True, "kafka",
                f"{cfg.osc.kafka.brokers} · {cfg.osc.kafka.security_protocol} · "
                f"group {cfg.osc.kafka.group_id}",
            )
        else:
            banner.check(False, "pm ingest", "no PM directory and no Kafka brokers")

        if cfg is not None:
            sftp = cfg.osc.sftp
            banner.check(
                sftp.enabled, "sftp pool",
                f"max idle {sftp.max_idle_seconds:.0f}s · "
                f"cleanup {sftp.cleanup_interval_seconds:.0f}s · "
                f"timeout {sftp.timeout_seconds:.0f}s"
                if sftp.enabled else "disabled — PM files are read from disk only",
            )
            sdnr = cfg.sdnr
            banner.check(
                sdnr.enabled, "sdnr",
                f"{sdnr.base_url} · node {sdnr.netconf_node_id or 'unset'}"
                if sdnr.enabled else "disabled — recommendations are not written back",
            )
            banner.check(
                _influx_live(), "influxdb",
                f"{cfg.influxdb.url} · bucket {cfg.influxdb.bucket}"
                if _influx_live() else "not configured — time-series disabled",
            )
        banner.check(True, "http server", f"uvicorn · {host}:{port}")
        banner.check(True, "signals", "SIGINT · SIGTERM → graceful shutdown")
        banner.blank()

        base = f"http://{host}:{port}"
        mode = (
            "closed-loop · SDNR apply armed"
            if cfg is not None and cfg.sdnr.enabled
            else "recommend-only · operator approval required"
        )
        banner.box(
            "READY",
            [
                ("Dashboard", f"{base}/ui/index.html"),
                ("API docs", f"{base}/docs"),
                ("Probes", "/healthz   /readyz   /startupz"),
                ("Metrics", "/metrics"),
                ("Mode", mode),
            ],
            f"booted in {(time.monotonic() - boot_started) * 1000:.0f}ms",
        )
        banner.blank()
        banner.rule("RUNTIME")

    def _uptime(seconds: float) -> str:
        hours, rest = divmod(int(seconds), 3600)
        minutes, secs = divmod(rest, 60)
        if hours:
            return f"{hours}h {minutes:02d}m {secs:02d}s"
        if minutes:
            return f"{minutes}m {secs:02d}s"
        return f"{seconds:.2f}s"

    async def _serve() -> None:
        started = time.monotonic()
        async with Orchestrator(fastapi_app=fastapi_app, host=host, port=port) as orch:
            _print_boot()
            await orch.shutdown_event.wait()
            uptime = time.monotonic() - started
            teardown = time.monotonic()
            cfg: AppConfig | None = getattr(fastapi_app.state, "config", None)
            cleanups = len(orch._extra_cleanup)

            banner.blank()
            banner.rule("SHUTDOWN")
            banner.arrow("signal", "shutdown requested — draining subsystems")
            banner.check(True, "readiness", "probes now report shutting-down")
            if _kafka_ingest(cfg):
                banner.check(
                    True, "pm ingest", "consumer stopped · partitions released",
                )
            banner.check(
                bool(cleanups), "cleanups",
                f"{cleanups} registered hook(s) drained" if cleanups
                else "none registered",
            )

        writer = getattr(fastapi_app.state, "influx_writer", None)
        stats = writer.stats() if writer is not None else {}
        banner.check(True, "http server", "in-flight requests drained · listener closed")
        banner.check(
            bool(stats.get("enabled")), "influxdb",
            f"{stats.get('writes_ok', 0)} points written · writer closed"
            if stats.get("enabled") else "was not running",
        )
        banner.blank()
        banner.box(
            "STOPPED",
            [
                ("Uptime", _uptime(uptime)),
                ("Teardown", f"{time.monotonic() - teardown:.2f}s"),
                ("Exit", "clean — every subsystem released"),
            ],
            f"pci-planning-and-optimization v{__version__}",
        )
        banner.blank()

    asyncio.run(_serve())


def main() -> None:
    cli(obj={})


if __name__ == "__main__":
    main()
