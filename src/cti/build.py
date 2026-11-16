"""Run the SQL models against the DuckDB warehouse, in filename order.

- src/cti/sql/*.sql         core models built straight from staging (`cti build`)
- src/cti/sql/marts/*.sql   models that need resolution output (`cti signals`, after `cti resolve`)

SQL files may reference {placeholders}; their values come only from prereg.yaml.
"""

from __future__ import annotations

from pathlib import Path

import duckdb

from cti.config import DATA_DIR, Config

SQL_DIR = Path(__file__).parent / "sql"
MARTS_DIR = SQL_DIR / "marts"


def _sql_list(xs) -> str:
    return ", ".join("'" + str(x).replace("'", "''") + "'" for x in xs)


def sql_params(cfg: Config, data_dir: Path = DATA_DIR) -> dict[str, str]:
    ins = cfg["groups"]["insider"]
    uni = cfg["universe"]
    return {
        "staging": (data_dir / "staging").as_posix(),
        "insider_codes": _sql_list(ins["codes"]),
        "insider_officer": str("officer" in ins["roles"]).upper(),
        "insider_director": str("director" in ins["roles"]).upper(),
        "insider_exclude_10b5_1": str(bool(ins["exclude_10b5_1"])).upper(),
        "insider_min_value_usd": str(float(ins["min_value_usd"])),
        "insider_title_exclude": ins["security_title_exclude_regex"].replace("'", "''"),
        "min_price": str(float(uni["min_price"])),
        "min_mcap_usd": str(float(uni["min_mcap_usd"])),
        "exchanges": _sql_list(uni["exchanges"]),
        "shares_lag_days": str(int(uni["shares_lag_days"])),
        "shares_max_age_days": str(int(uni["shares_max_age_days"])),
        "shares_fallback_lag_days": str(int(uni["shares_fallback_lag_days"])),
        "mcap_unknown": str(uni["mcap_unknown"]),
    }


def render(sql: str, params: dict[str, str]) -> str:
    # str.format would choke on SQL braces; replace only known keys.
    for k, v in params.items():
        sql = sql.replace("{" + k + "}", v)
    return sql


def _run(files: list[Path], cfg: Config, data_dir: Path) -> list[str]:
    params = sql_params(cfg, data_dir)
    con = duckdb.connect(str(data_dir / "warehouse.duckdb"))
    try:
        for f in files:
            con.execute(render(f.read_text(), params))
    finally:
        con.close()
    return [f.stem for f in files]


def build(cfg: Config, data_dir: Path = DATA_DIR, models: list[str] | None = None) -> list[str]:
    files = sorted(SQL_DIR.glob("*.sql"))
    if models:
        files = [f for f in files if f.stem in models]
    return _run(files, cfg, data_dir)


# Mart -> the input table it needs; marts whose input doesn't exist yet are skipped.
MART_REQUIRES = {"40_signals_insider": "signal_resolution", "41_signals_congress": "congress_resolution"}


def build_marts(cfg: Config, data_dir: Path = DATA_DIR) -> list[str]:
    con = duckdb.connect(str(data_dir / "warehouse.duckdb"), read_only=True)
    try:
        tables = {r[0] for r in con.execute("SELECT table_name FROM information_schema.tables").fetchall()}
    finally:
        con.close()
    files = [f for f in sorted(MARTS_DIR.glob("*.sql")) if MART_REQUIRES.get(f.stem, "") in tables | {""}]
    return _run(files, cfg, data_dir)
