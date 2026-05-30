"""Tests for the hardened README date updater (Phase 0)."""

from __future__ import annotations

import importlib.util
import re
from pathlib import Path

_SPEC = importlib.util.spec_from_file_location(
    "update_readme_date", Path(__file__).resolve().parent.parent / "update_readme_date.py"
)
urd = importlib.util.module_from_spec(_SPEC)
_SPEC.loader.exec_module(urd)


def test_get_last_friday_format():
    val = urd.get_last_friday()
    assert re.fullmatch(r"\d{4}-\d{2}-\d{2}", val)


def test_update_writes_when_pattern_present(tmp_path, monkeypatch):
    readme = tmp_path / "README.md"
    readme.write_text("cmd \\\n  --end   2020-01-01 \\\n  --outdir x\n")
    monkeypatch.setattr(urd, "README_PATH", readme)
    changed = urd.update_readme()
    assert changed is True
    assert urd.get_last_friday() in readme.read_text()


def test_no_match_is_safe_noop(tmp_path, monkeypatch, capsys):
    readme = tmp_path / "README.md"
    original = "no end-date command here\n"
    readme.write_text(original)
    monkeypatch.setattr(urd, "README_PATH", readme)
    changed = urd.update_readme()
    assert changed is False
    assert readme.read_text() == original  # unchanged, not silently rewritten


def test_missing_file_reports_and_returns_false(tmp_path, monkeypatch):
    monkeypatch.setattr(urd, "README_PATH", tmp_path / "does_not_exist.md")
    assert urd.update_readme() is False
