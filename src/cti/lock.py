"""Test-period lock.

- `tag_prereg` commits prereg.yaml and creates annotated tag prereg-v1 holding its hash.
- `assert_unlocked_for` refuses test-period work unless the current config matches the tag.
- `record_final_run` writes reports/test_results/RUN.json once; reruns need a logged reason.
"""

from __future__ import annotations

import datetime as dt
import json
import subprocess
from pathlib import Path

from cti.config import REPO_ROOT, REPORTS_DIR, Config, hash_bytes

TAG = "prereg-v1"
PREREG_REL = "prereg/prereg.yaml"
RUN_FILE = REPORTS_DIR / "test_results" / "RUN.json"


class LockError(RuntimeError):
    pass


def _git(*args: str, cwd: Path = REPO_ROOT) -> str:
    out = subprocess.run(["git", *args], cwd=cwd, capture_output=True, text=False)
    if out.returncode != 0:
        raise LockError(f"git {' '.join(args)} failed: {out.stderr.decode(errors='replace')}")
    return out.stdout.decode(errors="replace").strip()


def _git_bytes(*args: str, cwd: Path = REPO_ROOT) -> bytes:
    out = subprocess.run(["git", *args], cwd=cwd, capture_output=True)
    if out.returncode != 0:
        raise LockError(f"git {' '.join(args)} failed: {out.stderr.decode(errors='replace')}")
    return out.stdout


def tagged_hash(cwd: Path = REPO_ROOT) -> str:
    """Hash of prereg.yaml as stored in the tagged commit (not the tag message, which is editable)."""
    try:
        raw = _git_bytes("show", f"{TAG}:{PREREG_REL}", cwd=cwd)
    except LockError as e:
        raise LockError(f"No pre-registration tag {TAG!r} found. Run `cti prereg tag` first.") from e
    return hash_bytes(raw)


def tag_prereg(cfg: Config, cwd: Path = REPO_ROOT) -> str:
    existing = _git("tag", "--list", TAG, cwd=cwd)
    if existing:
        raise LockError(f"Tag {TAG} already exists. Pre-registration is one-time; bump to v2 deliberately.")
    _git("add", PREREG_REL, "prereg/PREREG.md", cwd=cwd)
    status = _git("status", "--porcelain", "--", "prereg", cwd=cwd)
    if status:
        _git("commit", "-m", f"Pre-registration v{cfg['version']} (sha256 {cfg.sha256[:12]})", cwd=cwd)
    _git("tag", "-a", TAG, "-m", f"prereg.yaml sha256={cfg.sha256}", cwd=cwd)
    return cfg.sha256


def assert_unlocked_for(period: str, cfg: Config, cwd: Path = REPO_ROOT) -> None:
    """Raise unless `period` may be computed with this config."""
    if period == "dev":
        return
    expected = tagged_hash(cwd)
    if cfg.sha256 != expected:
        raise LockError(
            f"prereg.yaml hash {cfg.sha256[:12]} does not match tag {TAG} ({expected[:12]}). "
            "Test-period runs must use the pre-registered config."
        )


def record_final_run(cfg: Config, outputs: dict, rerun: bool = False, reason: str | None = None,
                     run_file: Path = RUN_FILE, cwd: Path = REPO_ROOT) -> dict:
    assert_unlocked_for("test", cfg, cwd)
    history: list[dict] = []
    if run_file.exists():
        history = json.loads(run_file.read_text())["runs"]
        if not rerun:
            raise LockError("A --final test run already exists. Use --rerun --reason '...' (logged permanently).")
        if not reason:
            raise LockError("--rerun requires --reason.")
    entry = {
        "run_number": len(history) + 1,
        "timestamp_utc": dt.datetime.now(dt.UTC).isoformat(),
        "prereg_sha256": cfg.sha256,
        "git_commit": _git("rev-parse", "HEAD", cwd=cwd),
        "rerun_reason": reason,
        "outputs": outputs,
    }
    history.append(entry)
    run_file.parent.mkdir(parents=True, exist_ok=True)
    run_file.write_text(json.dumps({"runs": history}, indent=2, default=str))
    return entry
