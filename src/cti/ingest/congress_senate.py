"""Senate Periodic Transaction Reports (PTRs) from the Senate eFD site.

Search: https://efdsearch.senate.gov/search/  (requires accepting the public-use agreement once
        per session; the user accepted its terms on 2026-11-15)
PTR:    https://efdsearch.senate.gov/search/view/ptr/{uuid}/    electronic, an HTML table
Paper:  https://efdsearch.senate.gov/search/view/paper/{uuid}/  scanned images; counted, not parsed

Electronic PTRs are HTML tables with labeled columns (date, owner, ticker, asset name, asset type,
type, amount), so no text-layout parsing is needed. The client identifies itself honestly
("cti-research-prototype") and pauses between requests.

Raw files are immutable: data/raw/senate_ptr/{uuid}.html plus MANIFEST.json, and the search index
as a raw snapshot.
"""

from __future__ import annotations

import datetime as dt
import hashlib
import html as htmllib
import json
import re
import time
from pathlib import Path

import pandas as pd
import requests

from cti.config import DATA_DIR
from cti.ingest.raw import save_raw

BASE = "https://efdsearch.senate.gov"
UA = {"User-Agent": "cti-research-prototype"}
PAUSE_S = 3.0
PTR_REPORT_TYPE = 11

ASSET_TYPES = {"stock": "ST", "stock option": "OP", "other securities": "OT", "corporate bond": "CS",
               "municipal security": "GS", "non-public stock": "OL", "cryptocurrency": "CT",
               "commodities/futures contract": "FU", "other investment": "OT"}
TXN_TYPES = {"purchase": "P", "sale (full)": "S", "sale (partial)": "S", "sale": "S", "exchange": "E"}


def _with_net_retry(call, tries: int = 5, wait_s: int = 30):
    """Ride out a dropped connection (Wi-Fi, DNS, sleep). HTTP refusals are NOT retried here."""
    for i in range(tries):
        try:
            return call()
        except requests.ConnectionError:
            if i == tries - 1:
                raise
            time.sleep(wait_s * (i + 1))


class Session:
    """A requests session that has accepted the eFD agreement; re-accepts if the site drops it."""

    def __init__(self) -> None:
        self.s = requests.Session()
        self.s.headers.update(UA)
        self.accept()

    def accept(self) -> None:
        r = self.s.get(f"{BASE}/search/home/", timeout=60)
        r.raise_for_status()
        tok = re.search(r'name="csrfmiddlewaretoken" value="([^"]+)"', r.text)
        if not tok:
            raise RuntimeError("Senate eFD: agreement form not found (site layout or maintenance page)")
        form = {"csrfmiddlewaretoken": tok.group(1), "prohibition_agreement": "1"}
        r = self.s.post(f"{BASE}/search/home/", data=form,
                        headers={"Referer": f"{BASE}/search/home/"}, timeout=60, allow_redirects=False)
        if r.status_code != 302:
            raise RuntimeError(f"Senate eFD: agreement not accepted (HTTP {r.status_code})")

    def get(self, path: str) -> requests.Response:
        for attempt in range(3):
            r = _with_net_retry(lambda: self.s.get(f"{BASE}{path}", timeout=60, allow_redirects=False))
            if r.status_code in (301, 302) and "/home" in r.headers.get("Location", ""):
                self.accept()
                continue
            if r.status_code >= 500 and attempt < 2:
                time.sleep(10 * (attempt + 1))
                continue
            return r
        return r

    def search_page(self, start: int, length: int, since: str, until: str = "") -> dict:
        data = {"start": start, "length": length, "report_types": f"[{PTR_REPORT_TYPE}]", "filer_types": "[]",
                "submitted_start_date": f"{since} 00:00:00",
                "submitted_end_date": f"{until} 23:59:59" if until else "", "candidate_state": "",
                "senator_state": "", "office_id": "", "first_name": "", "last_name": ""}
        for attempt in range(2):
            r = _with_net_retry(lambda: self.s.post(
                f"{BASE}/search/report/data/", data=data, timeout=60,
                headers={"Referer": f"{BASE}/search/", "X-CSRFToken": self.s.cookies.get("csrftoken", "")}))
            if r.status_code == 200 and r.text.startswith("{"):
                return r.json()
            if attempt == 0:  # one slow retry, then stop: a refusal is the site's answer, not a thing to get around
                time.sleep(60)
        snippet = re.sub(r"\s+", " ", r.text[:200])
        raise RuntimeError(f"Senate eFD search refused at start={start} (HTTP {r.status_code}): {snippet}")


def parse_index_rows(rows: list[list[str]]) -> pd.DataFrame:
    """Search-result rows [first, last, office, link html, filed mm/dd/yyyy] -> one row per report."""
    out = []
    for first, last, office, link, filed in rows:
        m = re.search(r'href="/search/view/(ptr|paper)/([0-9a-f-]+)/"[^>]*>([^<]*)<', link)
        if not m:
            continue
        out.append({"doc_id": m.group(2), "electronic": m.group(1) == "ptr",
                    "title": htmllib.unescape(m.group(3)).strip(),
                    "first": first.strip(), "last": last.strip(), "office": office.strip(), "state_dst": "",
                    "filing_date": pd.to_datetime(filed, format="%m/%d/%Y", errors="coerce")})
    df = pd.DataFrame(out)
    if len(df):
        df["amendment"] = df["title"].str.contains("amendment", case=False)
        df["year"] = df["filing_date"].dt.year
    return df


def fetch_index(sess: Session, since: str = "01/01/2012", data_dir: Path = DATA_DIR, log=print) -> pd.DataFrame:
    """List every PTR one calendar month at a time. The search's paging has no stable sort order, so
    paging through all years at once repeats some reports and skips others; a month fits in one page."""
    rows = []
    months = pd.date_range(pd.to_datetime(since, format="%m/%d/%Y"), pd.Timestamp.today(), freq="MS")
    cache = data_dir / "staging" / "congress" / "senate_months"  # resume point; the raw snapshot is below
    cache.mkdir(parents=True, exist_ok=True)
    this_month = pd.Timestamp.today().normalize().replace(day=1)
    for k, m0 in enumerate(months, 1):
        m1 = m0 + pd.offsets.MonthEnd(0)
        cpath = cache / f"{m0:%Y-%m}.json"
        if cpath.exists() and m0 < this_month:  # a finished month's listing doesn't change
            rows += json.loads(cpath.read_text())
            continue
        got, start, total = [], 0, None
        while total is None or start < total:
            d = sess.search_page(start, 100, f"{m0:%m/%d/%Y}", f"{m1:%m/%d/%Y}")
            total = d["recordsTotal"]
            got += d["data"]
            start += 100
            time.sleep(PAUSE_S)
        if total > 100 and len({x[3] for x in got}) < total:
            log(f"senate index: {m0:%Y-%m} paging gave {len({x[3] for x in got})} of {total} distinct reports")
        rows += got
        cpath.write_text(json.dumps(got))
        if k % 12 == 0:
            log(f"senate index: through {m0:%Y-%m}, {len(rows):,} rows")
    save_raw("senate_index", "ptr_search_by_month.json", json.dumps(rows).encode(),
             url=f"{BASE}/search/report/data/",
             data_dir=data_dir)
    idx = parse_index_rows(rows).drop_duplicates("doc_id")
    log(f"senate index: {len(idx):,} PTRs, {int(idx['electronic'].sum()):,} electronic, "
        f"{int(idx['amendment'].sum()):,} amendments")
    return idx


def download_ptrs(idx: pd.DataFrame, sess: Session, data_dir: Path = DATA_DIR, log=print) -> int:
    d = data_dir / "raw" / "senate_ptr"
    d.mkdir(parents=True, exist_ok=True)
    mpath = d / "MANIFEST.json"
    manifest = json.loads(mpath.read_text()) if mpath.exists() else {}
    todo = [doc for doc in idx.loc[idx["electronic"], "doc_id"] if not (d / f"{doc}.html").exists()]
    n, refused = 0, 0
    for i, doc in enumerate(todo, 1):
        url = f"/search/view/ptr/{doc}/"
        r = sess.get(url)
        if r.status_code != 200 or "<table" not in r.text:
            manifest[f"{doc}.html"] = {"status": r.status_code, "url": BASE + url}
            refused = refused + 1 if r.status_code in (403, 429) else 0
            if refused >= 5:  # the site is refusing us: stop and keep what we have; rerun later resumes
                mpath.write_text(json.dumps(manifest, indent=1, sort_keys=True))
                log(f"senate ptr: stopped after {refused} refusals in a row (HTTP {r.status_code}); {n:,} saved")
                return n
            time.sleep(PAUSE_S)
            continue
        refused = 0
        path = d / f"{doc}.html"
        tmp = path.with_suffix(".part")
        tmp.write_bytes(r.content)
        tmp.replace(path)
        manifest[path.name] = {"sha256": hashlib.sha256(r.content).hexdigest(), "bytes": len(r.content),
                               "url": BASE + url, "fetched_utc": dt.datetime.now(dt.UTC).isoformat()}
        n += 1
        if i % 100 == 0:
            mpath.write_text(json.dumps(manifest, indent=1, sort_keys=True))
            log(f"senate ptr: {i:,}/{len(todo):,}")
        time.sleep(PAUSE_S)
    mpath.write_text(json.dumps(manifest, indent=1, sort_keys=True))
    return n


def _cell(s: str) -> str:
    return re.sub(r"\s+", " ", htmllib.unescape(re.sub(r"<[^>]+>", " ", s))).strip()


def _amount(s: str) -> tuple[int | None, int | None]:
    nums = [int(x.replace(",", "")) for x in re.findall(r"\$([\d,]+)", s)]
    if not nums:
        return None, None
    if s.lower().startswith("over"):
        return nums[0] + 1, None
    return nums[0], (nums[1] if len(nums) > 1 else None)


def parse_ptr_html(text: str) -> list[dict]:
    """The transactions table of one electronic Senate PTR -> House-parser-shaped rows."""
    tables = re.findall(r"<table[^>]*>(.*?)</table>", text, re.S)
    out = []
    for t in tables:
        rows = [[_cell(c) for c in re.findall(r"<t[dh][^>]*>(.*?)</t[dh]>", r, re.S)]
                for r in re.findall(r"<tr[^>]*>(.*?)</tr>", t, re.S)]
        if not rows or "Transaction Date" not in rows[0]:
            continue
        h = {name.lower(): i for i, name in enumerate(rows[0])}
        for row in rows[1:]:
            if len(row) < len(h):
                continue
            g = lambda k, row=row, h=h: row[h[k]] if k in h else ""  # noqa: E731
            tick = g("ticker").upper()
            if tick in ("", "--", "N/A"):  # some filers put the ticker in the asset name instead
                m = re.fullmatch(r"([A-Z]{1,5}(?:[.-][A-Z])?)", g("asset name").strip()) or \
                    re.search(r"\(([A-Z]{1,5}(?:[.-][A-Z])?)\)", g("asset name"))
                tick = m.group(1) if m else tick
            typ = g("type").lower()
            lo, hi = _amount(g("amount"))
            atype = g("asset type").lower()
            out.append({"owner": g("owner") or None, "asset": g("asset name"),
                        "ticker": None if tick in ("", "--", "N/A") else tick,
                        "asset_type": ASSET_TYPES.get(atype, "OT" if atype else None),
                        "asset_type_raw": g("asset type") or None,
                        "txn_type": TXN_TYPES.get(typ, typ[:1].upper() or None), "partial": "partial" in typ,
                        "trade_date": pd.to_datetime(g("transaction date"), format="%m/%d/%Y", errors="coerce"),
                        "amount_low": lo, "amount_high": hi, "comment": g("comment") or None})
    return out


def ingest(since: str = "01/01/2012", data_dir: Path = DATA_DIR, log=print) -> pd.DataFrame:
    sess = Session()
    idx = fetch_index(sess, since, data_dir, log)
    out = data_dir / "staging" / "congress"
    out.mkdir(parents=True, exist_ok=True)
    idx.to_parquet(out / "senate_index.parquet", index=False)
    download_ptrs(idx, sess, data_dir, log)
    return idx


DEDUP_KEY = ["last", "first", "owner", "trade_date", "txn_type", "amount_low", "_k"]


def dedupe_amendments(tx: pd.DataFrame) -> pd.DataFrame:
    """Drop a transaction only if the same senator reported it in a DIFFERENT, earlier report.
    Repeats within one report (two lots bought the same day) are real and kept."""
    t = tx.assign(_k=tx["ticker"].fillna(tx["asset"].str.upper()), _o=tx["owner"].fillna(""))
    t = t.drop(columns="owner").rename(columns={"_o": "owner"})
    key = DEDUP_KEY
    first = (t.sort_values(["filing_date", "doc_id"], kind="stable").groupby(key, dropna=False)["doc_id"]
             .first().rename("_first_doc"))
    t = t.join(first, on=key)
    keep = t["doc_id"] == t["_first_doc"]
    out = tx[keep.to_numpy()].reset_index(drop=True)
    out.attrs["dropped"] = int((~keep).sum())
    return out


def stage(data_dir: Path = DATA_DIR, log=print) -> pd.DataFrame:
    """Parse downloaded PTRs -> staging/congress/senate_transactions.parquet and senate_documents.parquet.

    An amendment replaces the report it amends, but eFD doesn't link the two. Amended reports are
    kept and their transactions deduplicated against the same senator's earlier ones on
    (trade date, ticker or asset, type, amount): the earliest filing wins, as for Form 4 amendments.
    """
    idx = pd.read_parquet(data_dir / "staging" / "congress" / "senate_index.parquet")
    raw = data_dir / "raw" / "senate_ptr"
    rows, status = [], {}
    for doc in idx.loc[idx["electronic"], "doc_id"]:
        p = raw / f"{doc}.html"
        if not p.exists():
            continue
        try:
            parsed = parse_ptr_html(p.read_text(encoding="utf-8", errors="replace"))
            status[doc] = "parsed" if parsed else "no_transactions_found"
            rows += [{"doc_id": doc, **r} for r in parsed]
        except Exception as e:  # one bad page must not kill the batch
            status[doc] = f"parse_error: {type(e).__name__}"[:60]
    tx = pd.DataFrame(rows)
    docs = idx.copy()
    docs["status"] = docs["doc_id"].map(status)
    docs.loc[~docs["electronic"], "status"] = "paper_scan_not_parsed"
    docs.loc[docs["electronic"] & docs["status"].isna(), "status"] = "not_downloaded"
    if len(tx):
        tx = tx.merge(idx[["doc_id", "last", "first", "state_dst", "filing_date"]], on="doc_id", how="left")
        tx = dedupe_amendments(tx)
        log(f"senate: {tx.attrs.get('dropped', 0):,} transactions repeated from an earlier report dropped")
    docs["n_transactions"] = docs["doc_id"].map(tx.groupby("doc_id").size() if len(tx) else {}).fillna(0)
    out = data_dir / "staging" / "congress"
    docs.to_parquet(out / "senate_documents.parquet", index=False)
    tx.to_parquet(out / "senate_transactions.parquet", index=False)
    log(f"senate parse: {len(tx):,} transactions; " +
        ", ".join(f"{k}={v:,}" for k, v in docs["status"].value_counts().items()))
    return tx
