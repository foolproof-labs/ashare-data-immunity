"""Tests for bar cleaning and validation."""

from __future__ import annotations

import pytest

from ashare_data_immunity.cleaning import clean_bars, validate_bars


def _bar(date="2026-08-01", open_=10.0, high=10.5, low=9.8, close=10.2, volume=1000.0) -> dict:
    return {"date": date, "open": open_, "high": high, "low": low, "close": close, "volume": volume}


def test_valid_bars_have_no_problems() -> None:
    assert validate_bars([_bar(), _bar("2026-08-02", close=10.5)]) == []


def test_missing_field_detected() -> None:
    bar = _bar()
    del bar["close"]
    problems = validate_bars([bar])
    assert any(p["kind"] == "missing_field" and p["field"] == "close" for p in problems)


def test_non_finite_detected() -> None:
    problems = validate_bars([_bar(close=float("nan"))])
    assert any(p["kind"] == "non_finite" for p in problems)


def test_non_positive_price_detected() -> None:
    problems = validate_bars([_bar(open_=0.0)])
    assert any(p["kind"] == "non_positive" and p["field"] == "open" for p in problems)


def test_ohlc_consistency_detected() -> None:
    problems = validate_bars([_bar(high=9.0)])  # high below open/close
    assert any(p["kind"] == "high_below_max_open_close" for p in problems)
    problems2 = validate_bars([_bar(low=10.4)])  # low above open/close
    assert any(p["kind"] == "low_above_min_open_close" for p in problems2)


def test_clean_bars_sanitizes_and_counts() -> None:
    bars = [_bar(), _bar("2026-08-02", close=float("nan")), _bar("2026-08-03", open_=-1.0)]
    cleaned, counts = clean_bars(bars)
    assert counts["non_finite"] == 1
    assert counts["non_positive"] == 1
    assert cleaned[1]["close"] is None
    assert cleaned[2]["open"] is None
    assert len(cleaned) == 3


def test_clean_bars_can_drop_non_positive() -> None:
    bars = [_bar(), _bar("2026-08-03", open_=-1.0)]
    cleaned, counts = clean_bars(bars, drop_non_positive=True)
    assert counts["dropped"] == 1
    assert len(cleaned) == 1
