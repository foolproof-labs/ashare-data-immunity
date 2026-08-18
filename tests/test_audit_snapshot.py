"""Tests for the quality audit and snapshot versioning."""

from __future__ import annotations

import json

import pytest

from ashare_data_immunity.audit import (
    continuity_problems,
    history_coverage,
    listing_problems,
    run_quality_audit,
)
from ashare_data_immunity.snapshot import build_snapshot, compare_snapshots


def test_listing_problems_finds_missing() -> None:
    result = listing_problems(
        ["600000", "300001", "999999"],
        [{"code": "600000"}, {"code": "300001"}],
    )
    assert result["not_in_current_universe"] == ["999999"]
    assert result["problem"] is True


def test_history_coverage_ratio(tmp_path) -> None:
    root = tmp_path / "history"
    root.mkdir()
    (root / "600000.json").write_text(json.dumps({"bars": [{"date": "2026-08-01"}]}), encoding="utf-8")
    (root / "000001.json").write_text(json.dumps({"bars": []}), encoding="utf-8")

    def loader(history_root, code):
        return __import__("ashare_data_immunity.audit", fromlist=["default_bars_loader"]).default_bars_loader(history_root, code)

    result = history_coverage(["600000", "000001"], loader, root)
    assert result["coverage"] == 0.5
    assert result["problem"] is True


def test_continuity_problems_detects_gap(tmp_path) -> None:
    root = tmp_path / "history"
    root.mkdir()
    bars = [{"date": "2026-01-05"}, {"date": "2026-02-20"}]
    (root / "600000.json").write_text(json.dumps({"bars": bars}), encoding="utf-8")

    def loader(history_root, code):
        return __import__("ashare_data_immunity.audit", fromlist=["default_bars_loader"]).default_bars_loader(history_root, code)

    problems = continuity_problems(["600000"], loader, root, max_gap_days=15)
    assert len(problems) == 1
    assert problems[0]["gaps"][0]["gap_days"] > 15


def test_run_quality_audit_writes_append_only(tmp_path) -> None:
    watchlist = tmp_path / "watchlist.json"
    watchlist.write_text(json.dumps({"eligible_codes": ["600000"]}), encoding="utf-8")
    history_root = tmp_path / "history"
    history_root.mkdir()
    (history_root / "600000.json").write_text(json.dumps({"bars": [{"date": "2026-08-01"}]}), encoding="utf-8")
    audit_root = tmp_path / "audit"

    record = run_quality_audit(
        watchlist_path=watchlist,
        history_root=history_root,
        audit_root=audit_root,
        universe_fetcher=lambda: [{"code": "600000"}],
    )
    assert record["passed"] is True
    assert record["listing"]["checked"] is True
    day_file = audit_root / f"{record['audit_date']}.jsonl"
    assert day_file.exists()
    # append-only: a second run adds a second line
    run_quality_audit(
        watchlist_path=watchlist,
        history_root=history_root,
        audit_root=audit_root,
        universe_fetcher=lambda: [{"code": "600000"}],
    )
    lines = day_file.read_text(encoding="utf-8").splitlines()
    assert len(lines) == 2


def test_snapshot_roundtrip_and_compare(tmp_path) -> None:
    root = tmp_path / "data"
    root.mkdir()
    (root / "a.json").write_text(json.dumps({"x": 1}), encoding="utf-8")
    (root / "b.json").write_text(json.dumps({"y": 2}), encoding="utf-8")

    first = build_snapshot(
        [root / "a.json", root / "b.json"], name="v1", cutoff="2026-08-01", root=root
    )
    assert first["file_count"] == 2
    assert "a.json" in first["files"]
    assert len(first["files"]["a.json"]) == 64

    # identical second build -> equal
    second = build_snapshot(
        [root / "a.json", root / "b.json"], name="v2", cutoff="2026-08-02", root=root
    )
    assert compare_snapshots(first, second)["equal"] is True

    # mutate a file -> changed
    (root / "a.json").write_text(json.dumps({"x": 2}), encoding="utf-8")
    third = build_snapshot(
        [root / "a.json", root / "b.json"], name="v3", cutoff="2026-08-03", root=root
    )
    result = compare_snapshots(first, third)
    assert result["equal"] is False
    assert result["changed"] == ["a.json"]

    # remove a file -> removed
    (root / "b.json").unlink()
    fourth = build_snapshot([root / "a.json"], name="v4", cutoff="2026-08-04", root=root)
    result = compare_snapshots(third, fourth)
    assert result["removed"] == ["b.json"]
