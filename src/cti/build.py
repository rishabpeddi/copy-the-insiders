"""Run the SQL models in src/cti/sql, in filename order, against the DuckDB warehouse.

SQL files may reference {placeholders}; their values come only from prereg.yaml.
"""

from __future__ import annotations

from pathlib import Path

import duckdb

from cti.config import DATA_DIR, Config

SQL_DIR = Path(__file__).parent / "sql"


def sql_params(cfg: Config, data_dir: Path = DATA_DIR) -> dict[str, str]:
    ins = cfg["groups"]["insider"]
    return {
        "staging": (data_dir / "staging").as_posix(),
        "insider_codes": ", ".join(f"'{c}'" for c in ins["codes"]),
        "insider_officer": str("officer" in ins["roles"]).upper(),
        "insider_director": str("director" in ins["roles"]).upper(),
        "insider_exclude_10b5_1": str(bool(ins["exclude_10b5_1"])).upper(),
        "insider_min_value_usd": str(float(ins["min_value_usd"])),
    }


def render(sql: str, params: dict[str, str]) -> str:
    # str.format would choke on SQL braces; replace only known keys.
    for k, v in params.items():
        sql = sql.replace("{" + k + "}", v)
    return sql


def build(cfg: Config, data_dir: Path = DATA_DIR, models: list[str] | None = None) -> list[str]:
    params = sql_params(cfg, data_dir)
    files = sorted(SQL_DIR.glob("*.sql"))
    if models:
        files = [f for f in files if f.stem in models]
    con = duckdb.connect(str(data_dir / "warehouse.duckdb"))
    try:
        for f in files:
            con.execute(render(f.read_text(), params))
    finally:
        con.close()
    return [f.stem for f in files]
