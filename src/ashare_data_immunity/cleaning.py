"""Bar cleaning and validation.

The immunity layer's first line: garbage in is flagged, never silently
propagated.  ``validate_bars`` reports problems per bar; ``clean_bars``
returns sanitized bars with problem counts so the caller can decide
whether to drop, quarantine, or proceed.
"""

from __future__ import annotations

import math
from typing import Any

REQUIRED_FIELDS = ("date", "open", "high", "low", "close", "volume")
NUMERIC_FIELDS = ("open", "high", "low", "close", "volume")


def _finite(value: Any) -> float | None:
    try:
        value = float(value)
    except (TypeError, ValueError):
        return None
    return value if math.isfinite(value) else None


def validate_bars(bars: list[dict[str, Any]]) -> list[dict[str, Any]]:
    """Return one problem record per bar (or per bar-field).

    Problem kinds: ``missing_field``, ``non_finite``, ``non_positive``,
    ``high_below_max_open_close``, ``low_above_min_open_close``,
    ``close_outside_high_low``, ``negative_volume``.
    """
    problems: list[dict[str, Any]] = []
    for index, bar in enumerate(bars or []):
        date_text = str(bar.get("date") or "")[:10]
        for field in REQUIRED_FIELDS:
            if field not in bar or bar[field] is None:
                problems.append(
                    {"bar": index, "date": date_text, "kind": "missing_field", "field": field}
                )
                continue
            if field == "date":
                continue  # date is required but not numeric
            value = _finite(bar[field])
            if value is None:
                problems.append(
                    {"bar": index, "date": date_text, "kind": "non_finite", "field": field}
                )
            elif field != "volume" and value <= 0:
                problems.append(
                    {"bar": index, "date": date_text, "kind": "non_positive", "field": field}
                )
            elif field == "volume" and value < 0:
                problems.append(
                    {"bar": index, "date": date_text, "kind": "negative_volume", "field": field}
                )
        high = _finite(bar.get("high"))
        low = _finite(bar.get("low"))
        open_ = _finite(bar.get("open"))
        close = _finite(bar.get("close"))
        if None not in (high, low, open_, close):
            if high < max(open_, close) - 1e-9:
                problems.append(
                    {"bar": index, "date": date_text, "kind": "high_below_max_open_close"}
                )
            if low > min(open_, close) + 1e-9:
                problems.append(
                    {"bar": index, "date": date_text, "kind": "low_above_min_open_close"}
                )
    return problems


def clean_bars(
    bars: list[dict[str, Any]],
    *,
    drop_non_positive: bool = False,
) -> tuple[list[dict[str, Any]], dict[str, int]]:
    """Sanitize bars: NaN/Inf -> None, non-positive prices -> None (or drop).

    Returns ``(cleaned_bars, counts)`` where counts tallies
    ``cleaned``, ``non_finite``, ``non_positive``, ``dropped`` and
    ``problems`` (OHLCV inconsistencies found).
    """
    problems = validate_bars(bars)
    counts: dict[str, int] = {
        "cleaned": 0,
        "non_finite": 0,
        "non_positive": 0,
        "dropped": 0,
        "problems": len(problems),
    }
    by_bar: dict[int, list[dict[str, Any]]] = {}
    for problem in problems:
        by_bar.setdefault(problem["bar"], []).append(problem)
    cleaned: list[dict[str, Any]] = []
    for index, bar in enumerate(bars or []):
        bar_problems = by_bar.get(index, [])
        counts["non_finite"] += sum(1 for p in bar_problems if p["kind"] == "non_finite")
        non_positive = any(p["kind"] == "non_positive" for p in bar_problems)
        if non_positive:
            counts["non_positive"] += 1
            if drop_non_positive:
                counts["dropped"] += 1
                continue
        out = dict(bar)
        for field in ("open", "high", "low", "close"):
            value = _finite(out.get(field))
            out[field] = value if value is not None and value > 0 else None
        volume = _finite(out.get("volume"))
        out["volume"] = volume if volume is not None and volume >= 0 else None
        counts["cleaned"] += 1
        cleaned.append(out)
    return cleaned, counts
