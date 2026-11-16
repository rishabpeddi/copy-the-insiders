"""Parse House PTR text (from pdfplumber) into transaction rows.

Layouts changed over the years (field labels are sometimes blanked out, fonts mangle letter case,
cells wrap onto following lines), so parsing anchors on what every transaction row has:

    <type> <transaction date> <notification date> <amount>     e.g.  "P 02/28/2020 03/20/2020 $1,001 - $15,000"

The asset (with "(TICKER)" and "[ST]") is the text before the type on that line plus up to a few
wrapped continuation lines after it. Label lines ("Filing status: New", "Subholding of: ...",
"Description: ..."), page headers, and the next anchor end a row.
"""

from __future__ import annotations

import re

import pandas as pd
import pdfplumber

# House PTR amount brackets: the low end determines the high end.
BRACKETS = {1_001: 15_000, 15_001: 50_000, 50_001: 100_000, 100_001: 250_000, 250_001: 500_000,
            500_001: 1_000_000, 1_000_001: 5_000_000, 5_000_001: 25_000_000, 25_000_001: 50_000_000}
_DATE = r"\d{1,2}/\d{1,2}/\d{4}"
ANCHOR = re.compile(
    rf"(?:^|\s)(?P<type>[PSEpse](?:\s*\(partial\))?)\s+(?P<tdate>{_DATE})\s+(?P<ndate>{_DATE})\s+"
    r"(?P<amount>\$[\d,]+(?:\s*-\s*(?:\$[\d,]+)?)?|(?:spouse/dc\s+)?over(?:\s+\$[\d,]+)?)",
    re.IGNORECASE)
# "FILING STATuS: New", "S          O : x" (blanked labels use odd whitespace glyphs)
_LABEL = re.compile(r"^[^$()\[\]:]{1,45}:(\s|$)")
_HEADER = re.compile(r"^(id\s+owner|type\s+date|\$200\?|gains\s*>|\* for the complete|filing id)", re.I)
_OWNER = re.compile(r"^(SP|JT|DC)\s+")
_TICKER = re.compile(r"\(([A-Za-z][A-Za-z0-9.\-]{0,9})\)")
_ATYPE = re.compile(r"\[([A-Za-z]{2})\]")
_AMOUNT_ONLY = re.compile(r"^\$[\d,]+$")


def _amount(text: str) -> tuple[float | None, float | None]:
    nums = [int(x.replace(",", "")) for x in re.findall(r"\$([\d,]+)", text)]
    if not nums:
        return None, None
    lo = nums[0]
    if text.lower().startswith(("over", "spouse")):
        return float(lo + 1), None  # "Over $1,000,000": open-ended
    return float(lo), float(BRACKETS.get(lo, nums[1] if len(nums) > 1 else lo))


def parse_text(text: str) -> list[dict]:
    lines = [ln.strip() for ln in text.splitlines()]
    rows = []
    for i, line in enumerate(lines):
        m = ANCHOR.search(line)
        if not m:
            continue
        asset = line[:m.start()].strip()
        # Wrapped continuation lines: ticker, asset code, the rest of the name, the amount's high end.
        for nxt in lines[i + 1:i + 4]:
            if not nxt or ANCHOR.search(nxt) or _LABEL.match(nxt) or _HEADER.match(nxt):
                break
            if _AMOUNT_ONLY.match(nxt):
                continue
            asset += " " + re.sub(r"\s*\$[\d,]+$", "", nxt)
        owner = None
        om = _OWNER.match(asset)
        if om:
            owner, asset = om.group(1), asset[om.end():]
        tickers = _TICKER.findall(asset)
        atypes = _ATYPE.findall(asset)
        t = m.group("type").upper().replace(" ", "")
        amount = m.group("amount")
        if "$" not in amount and i + 1 < len(lines):  # "Spouse/DC Over" + "$1,000,000" on the next line
            amount += " " + lines[i + 1]
        lo, hi = _amount(amount)
        rows.append({
            "owner": owner,
            "asset": re.sub(r"\s+", " ", _ATYPE.sub("", asset)).strip(),
            "ticker": tickers[-1].upper() if tickers else None,
            "asset_type": atypes[-1].upper() if atypes else None,
            "txn_type": {"P": "P", "S": "S", "S(PARTIAL)": "S", "E": "E"}.get(t, t),
            "partial": "PARTIAL" in t,
            "trade_date": pd.to_datetime(m.group("tdate"), format="%m/%d/%Y", errors="coerce"),
            "notification_date": pd.to_datetime(m.group("ndate"), format="%m/%d/%Y", errors="coerce"),
            "amount_low": lo, "amount_high": hi,
        })
    return rows


def pdf_text(path) -> str:
    with pdfplumber.open(path) as pdf:
        return "\n".join((p.extract_text() or "") for p in pdf.pages)
