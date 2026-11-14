"""Tiny builders for hand-calculated fixture portfolios."""

from __future__ import annotations

import datetime as dt

import pandas as pd

D0 = dt.date(2020, 1, 6)  # a Monday


def cal(n: int) -> list[dt.date]:
    """n consecutive weekdays starting at D0 (d0..d{n-1})."""
    return list(pd.bdate_range(D0, periods=n).date)


def prices(rows: list[tuple]) -> pd.DataFrame:
    """rows: (security_id, day_index, open, close[, delist_return])."""
    days = cal(max(r[1] for r in rows) + 1)
    out = []
    for r in rows:
        dr = r[4] if len(r) > 4 else None
        out.append({"security_id": r[0], "date": days[r[1]], "open": r[2], "close": r[3],
                    "delist_return": dr})
    return pd.DataFrame(out)


def signal(sid: str, side: str, sec: str, filer: str, entry_day: int, n_days: int) -> dict:
    days = cal(n_days)
    entry = days[entry_day]
    public = entry - dt.timedelta(days=1)
    return {"signal_id": sid, "side": side, "security_id": sec, "filer_id": filer,
            "public_date": public, "entry_date": entry}


def signals(*rows: dict) -> pd.DataFrame:
    return pd.DataFrame(list(rows))
