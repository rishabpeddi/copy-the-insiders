"""Immutable raw snapshots shared by every adapter.

Sources that change over time (ticker maps, rate series, vendor prices) are saved as dated
snapshots: data/raw/<source>/<YYYYMMDD>/<name>. A snapshot is never overwritten; each source
directory has a MANIFEST.json with the sha256, size and fetch time of every file.
"""

from __future__ import annotations

import datetime as dt
import hashlib
import json
from pathlib import Path

from cti.config import DATA_DIR


def today_tag() -> str:
    return dt.date.today().strftime("%Y%m%d")


def snapshot_dir(source: str, tag: str | None = None, data_dir: Path = DATA_DIR) -> Path:
    return data_dir / "raw" / source / (tag or today_tag())


def save_raw(source: str, name: str, content: bytes, url: str | None = None,
             tag: str | None = None, data_dir: Path = DATA_DIR) -> Path:
    d = snapshot_dir(source, tag, data_dir)
    d.mkdir(parents=True, exist_ok=True)
    path = d / name
    digest = hashlib.sha256(content).hexdigest()
    manifest_path = data_dir / "raw" / source / "MANIFEST.json"
    manifest = json.loads(manifest_path.read_text()) if manifest_path.exists() else {}
    key = f"{d.name}/{name}"
    if path.exists():
        if manifest.get(key, {}).get("sha256") not in (None, digest):
            raise RuntimeError(f"{key} already exists with different content; raw snapshots are immutable")
        return path
    tmp = path.with_suffix(path.suffix + ".part")
    tmp.write_bytes(content)
    tmp.replace(path)
    manifest[key] = {"sha256": digest, "bytes": len(content), "url": url,
                     "fetched_utc": dt.datetime.now(dt.UTC).isoformat()}
    manifest_path.write_text(json.dumps(manifest, indent=2, sort_keys=True))
    return path


def latest_snapshot(source: str, name: str, data_dir: Path = DATA_DIR) -> Path:
    root = data_dir / "raw" / source
    hits = sorted(root.glob(f"*/{name}"))
    if not hits:
        raise FileNotFoundError(f"No raw snapshot of {source}/{name}. Run the matching `cti ingest` command.")
    return hits[-1]
