"""The test-period lock, exercised in a throwaway git repo."""

from __future__ import annotations

import shutil
import subprocess
from pathlib import Path

import pytest

from cti.config import PREREG_PATH, load_config
from cti.lock import LockError, assert_unlocked_for, record_final_run, tag_prereg


@pytest.fixture
def repo(tmp_path: Path) -> Path:
    (tmp_path / "prereg").mkdir()
    shutil.copy(PREREG_PATH, tmp_path / "prereg" / "prereg.yaml")
    (tmp_path / "prereg" / "PREREG.md").write_text("draft\n")
    for args in (["init", "-q"], ["config", "user.email", "t@example.com"], ["config", "user.name", "t"],
                 ["config", "commit.gpgsign", "false"], ["config", "tag.gpgsign", "false"]):
        subprocess.run(["git", *args], cwd=tmp_path, check=True)
    return tmp_path


def test_dev_is_always_allowed(repo):
    assert_unlocked_for("dev", load_config(repo / "prereg" / "prereg.yaml"), cwd=repo)


def test_test_period_refused_before_tag(repo):
    cfg = load_config(repo / "prereg" / "prereg.yaml")
    with pytest.raises(LockError, match="No pre-registration tag"):
        assert_unlocked_for("test", cfg, cwd=repo)


def test_tag_then_edit_is_refused(repo):
    path = repo / "prereg" / "prereg.yaml"
    tag_prereg(load_config(path), cwd=repo)
    assert_unlocked_for("test", load_config(path), cwd=repo)

    path.write_text(path.read_text().replace("hold_trading_days: 126", "hold_trading_days: 63", 1))
    with pytest.raises(LockError, match="does not match"):
        assert_unlocked_for("test", load_config(path), cwd=repo)


def test_crlf_checkout_hashes_the_same(repo):
    path = repo / "prereg" / "prereg.yaml"
    tag_prereg(load_config(path), cwd=repo)
    path.write_bytes(path.read_bytes().replace(b"\r\n", b"\n").replace(b"\n", b"\r\n"))
    assert_unlocked_for("test", load_config(path), cwd=repo)


def test_second_final_run_needs_logged_reason(repo):
    path = repo / "prereg" / "prereg.yaml"
    cfg = load_config(path)
    tag_prereg(cfg, cwd=repo)
    run_file = repo / "reports" / "RUN.json"
    record_final_run(cfg, {"ok": 1}, run_file=run_file, cwd=repo)
    with pytest.raises(LockError, match="already exists"):
        record_final_run(cfg, {"ok": 2}, run_file=run_file, cwd=repo)
    with pytest.raises(LockError, match="requires --reason"):
        record_final_run(cfg, {"ok": 2}, rerun=True, run_file=run_file, cwd=repo)
    entry = record_final_run(cfg, {"ok": 2}, rerun=True, reason="fixed split bug", run_file=run_file, cwd=repo)
    assert entry["run_number"] == 2 and entry["rerun_reason"] == "fixed split bug"


def test_tag_is_one_time(repo):
    cfg = load_config(repo / "prereg" / "prereg.yaml")
    tag_prereg(cfg, cwd=repo)
    with pytest.raises(LockError, match="already exists"):
        tag_prereg(cfg, cwd=repo)
