"""Load prereg.yaml and compute its hash. The only place rules come from."""

from __future__ import annotations

import datetime as dt
import hashlib
from dataclasses import dataclass
from pathlib import Path
from typing import Any

import yaml

REPO_ROOT = Path(__file__).resolve().parents[2]
PREREG_PATH = REPO_ROOT / "prereg" / "prereg.yaml"
DATA_DIR = REPO_ROOT / "data"
REPORTS_DIR = REPO_ROOT / "reports"


def hash_bytes(raw: bytes) -> str:
    """SHA-256 with line endings normalized, so Windows checkouts hash the same as Linux CI."""
    normalized = raw.replace(b"\r\n", b"\n")
    return hashlib.sha256(normalized).hexdigest()


@dataclass(frozen=True)
class Config:
    raw: dict[str, Any]
    sha256: str
    path: Path

    def __getitem__(self, key: str) -> Any:
        return self.raw[key]

    def period(self, name: str) -> tuple[dt.date, dt.date | None]:
        p = self.raw["periods"][name]
        return p["start"], p.get("end")

    @property
    def portfolio(self) -> dict[str, Any]:
        return self.raw["portfolio"]

    def cost_bps(self, scenario: str = "base") -> float:
        return float(self.raw["costs"][f"{scenario}_bps_per_side"])


REQUIRED_KEYS = {"version", "periods", "universe", "groups", "portfolio", "delisting",
                 "costs", "benchmarks", "inference", "decision_rule", "sensitivity", "data", "resolution"}


def load_config(path: Path = PREREG_PATH) -> Config:
    raw_bytes = path.read_bytes()
    data = yaml.safe_load(raw_bytes)
    missing = REQUIRED_KEYS - set(data)
    if missing:
        raise ValueError(f"prereg.yaml is missing sections: {sorted(missing)}")
    return Config(raw=data, sha256=hash_bytes(raw_bytes), path=path)
