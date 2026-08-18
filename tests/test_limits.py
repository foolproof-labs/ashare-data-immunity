"""Tests for board-aware price-limit and suspension detection."""

from __future__ import annotations

import pytest

from ashare_data_immunity.limits import (
    board_of,
    detect_limits,
    price_limit_ratio,
    suspension_days,
)


def _bar(date, close, volume=1000.0, open_=None, high=None, low=None) -> dict:
    open_ = open_ if open_ is not None else close
    high = high if high is not None else close
    low = low if low is not None else close
    return {"date": date, "open": open_, "high": high, "low": low, "close": close, "volume": volume}


def test_board_classification() -> None:
    assert board_of("600000") == "main"
    assert board_of("000001") == "main"
    assert board_of("688001") == "star"
    assert board_of("689009") == "star"
    assert board_of("300750") == "chinext"
    assert board_of("301001") == "chinext"
    assert board_of("920001") == "bse"


def test_price_limit_ratios() -> None:
    assert price_limit_ratio("600000") == pytest.approx(0.10)
    assert price_limit_ratio("688001") == pytest.approx(0.20)
    assert price_limit_ratio("300750") == pytest.approx(0.20)
    assert price_limit_ratio("920001") == pytest.approx(0.30)
    assert price_limit_ratio("600000", is_st=True) == pytest.approx(0.05)
    assert price_limit_ratio("688001", is_st=True) == pytest.approx(0.20)  # STAR ST stays 20%


def test_detect_limit_up() -> None:
    bars = [
        _bar("2026-08-03", close=10.00),
        _bar("2026-08-04", close=11.00),  # +10% exactly -> limit up
        _bar("2026-08-05", close=12.00),  # not a limit (+9.09%)
    ]
    events = detect_limits(bars, "600000")
    assert len(events) == 1
    assert events[0]["date"] == "2026-08-04"
    assert events[0]["limit_up"] is True
    assert events[0]["limit_down"] is False


def test_detect_limit_down() -> None:
    bars = [
        _bar("2026-08-03", close=10.00),
        _bar("2026-08-04", close=9.00),  # -10% exactly -> limit down
    ]
    events = detect_limits(bars, "600000")
    assert len(events) == 1
    assert events[0]["limit_down"] is True


def test_rounding_tolerance() -> None:
    # 10.00 * 1.1 = 11.000000000000002 -> rounds to 11.00; a vendor value of
    # 11.001 is within tolerance of the rounded limit price.
    bars = [
        _bar("2026-08-03", close=10.00),
        _bar("2026-08-04", close=11.001),
    ]
    events = detect_limits(bars, "600000", tolerance=0.002)
    assert len(events) == 1


def test_st_ratio_narrows_limit() -> None:
    bars = [
        _bar("2026-08-03", close=10.00),
        _bar("2026-08-04", close=10.50),  # +5%: ST limit up, but NOT a main-board limit
    ]
    assert detect_limits(bars, "600000") == []  # +5% is not +10%
    events = detect_limits(bars, "600000", is_st=True)
    assert len(events) == 1
    assert events[0]["limit_up"] is True


def test_star_20_percent() -> None:
    bars = [
        _bar("2026-08-03", close=20.00),
        _bar("2026-08-04", close=24.00),  # +20% STAR limit up
    ]
    events = detect_limits(bars, "688001")
    assert len(events) == 1
    assert events[0]["limit_up"] is True


def test_suspension_zero_volume() -> None:
    bars = [
        _bar("2026-08-03", close=10.00, volume=1000.0),
        _bar("2026-08-04", close=10.00, volume=0.0),
        _bar("2026-08-05", close=10.00, volume=1000.0),
    ]
    days = suspension_days(bars)
    assert [d["date"] for d in days] == ["2026-08-04"]
    assert days[0]["reason"] == "zero_volume"


def test_suspension_no_prices() -> None:
    bars = [
        _bar("2026-08-03", close=10.00),
        {"date": "2026-08-04", "open": None, "high": None, "low": None, "close": None, "volume": 0},
        _bar("2026-08-05", close=10.00),
    ]
    days = suspension_days(bars)
    assert [d["date"] for d in days] == ["2026-08-04"]
    assert days[0]["reason"] == "no_prices"
