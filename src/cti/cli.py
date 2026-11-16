"""cti command line. `cti all` mirrors `make all` for machines without make."""

from __future__ import annotations

import subprocess
import sys

import typer

from cti.config import REPO_ROOT, load_config

app = typer.Typer(help="copy-the-insiders pipeline", no_args_is_help=True)
ingest_app = typer.Typer(help="Download raw data and stage it", no_args_is_help=True)
prereg_app = typer.Typer(help="Pre-registration hash and tag", no_args_is_help=True)
app.add_typer(ingest_app, name="ingest")
app.add_typer(prereg_app, name="prereg")


@ingest_app.command("form4")
def ingest_form4(start: str = "2014Q1", end: str = "2026Q3") -> None:
    """SEC insider transaction datasets -> data/raw/form4 -> data/staging/form4."""
    from cti.ingest.sec_form4 import ingest

    ingest(start, end, log=lambda m: typer.echo(m))


@ingest_app.command("reference")
def ingest_reference() -> None:
    """T-bills (US Treasury), SEC CIK->ticker map, SPY + 11 sector ETF prices."""
    from cti.pipeline import ingest_reference as run

    out = run(load_config())
    typer.echo(f"reference tickers: {', '.join(out['reference_tickers'])}")
    if out["missing"]:
        typer.echo(f"MISSING: {out['missing']}", err=True)


@ingest_app.command("prices")
def ingest_prices(refetch: bool = typer.Option(False, help="Re-pull tickers already staged")) -> None:
    """Prices for every ticker the insider candidates could map to. Run `cti build` first."""
    from cti.pipeline import ingest_prices as run

    n = run(load_config(), only_missing=not refetch, log=lambda m: typer.echo(m))["requested"]
    typer.echo(f"fetched {n} tickers")


@app.command()
def resolve() -> None:
    """Match candidates to securities, write warehouse tables and reports/data_quality.md."""
    from cti.pipeline import run_resolution

    s = run_resolution(load_config())
    typer.echo(f"matched {s['matched']:,} / {s['candidates']:,} ({s['match_rate']:.1%})")
    for k, v in s["reasons"].items():
        typer.echo(f"  unmatched {k}: {v:,}")
    typer.echo("report: reports/data_quality.md  audit: reports/audit/match_audit_sample.csv")


@app.command()
def build(model: list[str] = typer.Option(None, help="Only run these SQL models (file stems)")) -> None:
    """Run SQL models into data/warehouse.duckdb."""
    from cti.build import build as run_build

    for m in run_build(load_config(), models=model):
        typer.echo(f"built {m}")


@prereg_app.command("hash")
def prereg_hash() -> None:
    typer.echo(load_config().sha256)


@prereg_app.command("tag")
def prereg_tag() -> None:
    """Commit prereg.yaml and create tag prereg-v1. Then run `git push origin prereg-v1`."""
    from cti.lock import tag_prereg

    h = tag_prereg(load_config())
    typer.echo(f"Tagged prereg-v1 sha256={h}\nNow push it so the timestamp is public: git push origin prereg-v1")


@app.command("run")
def run_cmd(period: str = typer.Option("dev", help="dev | test"),
            final: bool = False, rerun: bool = False, reason: str = "",
            group: str = typer.Option("insider", help="insider | congress"),
            only: list[str] = typer.Option(None, help="Run only these scenario names")) -> None:
    """Backtest a period: the primary scenario plus every pre-registered sensitivity run."""
    from cti.lock import assert_unlocked_for

    cfg = load_config()
    if period not in {"dev", "test"}:
        raise typer.BadParameter("period must be dev or test")
    assert_unlocked_for(period, cfg)
    if period == "test":
        if not final:
            raise typer.BadParameter("Test-period runs are one-time: pass --final.")
        typer.echo("The --final test run (Holm adjustment + decision rule) is Phase 6 and not wired yet.")
        raise typer.Exit(code=1)

    from cti.backtest.report import write_dev_report
    from cti.backtest.runner import run_period

    run_period(cfg, period, group=group, only=only or None, log=lambda m: typer.echo(m))
    typer.echo(f"report: {write_dev_report(cfg, group=group)}")


@ingest_app.command("shares")
def ingest_shares() -> None:
    """Point-in-time shares outstanding (SEC XBRL frames) for the market-cap filter."""
    from cti.ingest import sec_shares

    sec_shares.fetch(int(str(load_config()["data"]["price_history_start"])[:4]),
                     log=lambda m: None if "none yet" in m else typer.echo(m))
    typer.echo(f"staged {len(sec_shares.stage()):,} share counts")


@app.command()
def signals() -> None:
    """Universe filter + buy/sell signals (SQL marts). Run after `cti resolve`."""
    import duckdb

    from cti.build import build_marts
    from cti.config import DATA_DIR

    built = build_marts(load_config())
    con = duckdb.connect(str(DATA_DIR / "warehouse.duckdb"), read_only=True)
    try:
        for g in ("insider", "congress"):
            if not any(b.endswith(g) for b in built):
                continue
            typer.echo(f"{g}:")
            for r, n in con.execute(f"SELECT coalesce(universe_reason, 'PASS'), count(*) FROM signals_{g}_all "
                                    "GROUP BY 1 ORDER BY 2 DESC").fetchall():
                typer.echo(f"  {r}: {n:,}")
            typer.echo(f"  buy signals: {con.execute(f'SELECT count(*) FROM signals_{g}').fetchone()[0]:,}; "
                       f"sell signals: {con.execute(f'SELECT count(*) FROM signals_{g}_sells').fetchone()[0]:,}")
    finally:
        con.close()


@ingest_app.command("congress")
def ingest_congress(start: int = 2015, end: int = 2026) -> None:
    """House PTR index + electronic PDFs (House Clerk), then parse to staging."""
    from cti.ingest import congress_house

    congress_house.ingest(start, end, log=lambda m: typer.echo(m))
    congress_house.stage(log=lambda m: typer.echo(m))


@app.command("resolve-congress")
def resolve_congress(fetch_prices: bool = typer.Option(True, help="Fetch prices for newly mapped tickers")) -> None:
    """Match House transactions to securities; writes congress_resolution and data_quality_congress.md."""
    from cti import congress_pipeline as cp

    cfg = load_config()
    if fetch_prices:
        typer.echo(f"fetched {cp.ingest_prices(cfg, log=lambda m: typer.echo(m))} new tickers")
    s = cp.run_resolution(cfg)
    typer.echo(f"matched {s['matched']:,} / {s['in_scope']:,} in-scope ({s['matched'] / max(s['in_scope'], 1):.1%})")
    typer.echo("report: reports/data_quality_congress.md")


@app.command("all")
def all_cmd(start: str = "2014Q1", end: str = "2026Q3", skip_ingest: bool = False) -> None:
    """Ingest, build, resolve, signals, dev backtest, tests. Same as `make all`."""
    if not skip_ingest:
        ingest_form4(start, end)
    build(None)
    if not skip_ingest:
        ingest_reference()
        ingest_prices(False)
        ingest_shares()
    resolve()
    signals()
    run_cmd("dev", False, False, "", "insider", None)
    run_cmd("dev", False, False, "", "congress", None)
    raise typer.Exit(subprocess.call([sys.executable, "-m", "pytest", "-q"], cwd=REPO_ROOT))


if __name__ == "__main__":
    app()
