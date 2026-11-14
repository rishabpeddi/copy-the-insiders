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
def ingest_form4(start: str = "2014Q1", end: str = "2026Q2") -> None:
    """SEC insider transaction datasets -> data/raw/form4 -> data/staging/form4."""
    from cti.ingest.sec_form4 import ingest

    for q, counts in ingest(start, end).items():
        typer.echo(f"{q}: " + ", ".join(f"{k}={v:,}" for k, v in counts.items()))


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
            final: bool = False, rerun: bool = False, reason: str = "") -> None:
    """Backtest a period. Test-period runs require the tagged config and --final."""
    from cti.lock import assert_unlocked_for

    cfg = load_config()
    if period not in {"dev", "test"}:
        raise typer.BadParameter("period must be dev or test")
    assert_unlocked_for(period, cfg)
    if period == "test" and not final:
        raise typer.BadParameter("Test-period runs are one-time: pass --final.")
    typer.echo("Backtest wiring lands in Phase 4 (needs prices + security resolution from Phase 2).")
    raise typer.Exit(code=1)


@app.command("all")
def all_cmd(start: str = "2014Q1", end: str = "2026Q2", skip_ingest: bool = False) -> None:
    """Ingest, build, test. Same as `make all`."""
    if not skip_ingest:
        ingest_form4(start, end)
    build(None)
    raise typer.Exit(subprocess.call([sys.executable, "-m", "pytest", "-q"], cwd=REPO_ROOT))


if __name__ == "__main__":
    app()
