"""Quality audit with injectable data sources.

The audit answers three daily questions about a watchlist:

1. **listing** — are the watched codes still in the current universe?
   (delisting / suspension check; the universe source is injectable —
   network fetchers are the caller's business)
2. **coverage** — what fraction of the watchlist has daily history?
3. **continuity** — which codes have calendar gaps beyond a threshold?

Everything is read-only; results are appended to a JSONL audit file.
"""

from __future__ import annotations

import json
from datetime import date, datetime, timedelta
from pathlib import Path
from typing import Any, Callable

MIN_HISTORY_COVERAGE = 0.8
MAX_CALENDAR_GAP_DAYS = 15

UniverseFetcher = Callable[[], list[dict[str, Any]]]
WatchlistLoader = Callable[[Path], dict[str, Any]]
BarsLoader = Callable[[Path, str], list[dict[str, Any]]]


def _watchlist_codes(payload: dict[str, Any]) -> list[str]:
    eligible = payload.get("eligible_codes")
    if isinstance(eligible, list):
        return sorted({str(code).strip() for code in eligible if str(code).strip()})
    members = payload.get("members") or []
    return sorted(
        {
            str(item.get("code") or "").strip()
            for item in members
            if str(item.get("code") or "").strip()
        }
    )


def default_watchlist_loader(path: Path) -> dict[str, Any]:
    try:
        payload = json.loads(path.read_text(encoding="utf-8"))
    except (OSError, json.JSONDecodeError):
        return {}
    return payload if isinstance(payload, dict) else {}


def default_bars_loader(history_root: Path, code: str) -> list[dict[str, Any]]:
    """Load ``<history_root>/<code>.json`` with a ``bars`` list."""
    try:
        payload = json.loads((history_root / f"{code}.json").read_text(encoding="utf-8"))
    except (OSError, json.JSONDecodeError):
        return []
    bars = payload.get("bars") or []
    return bars if isinstance(bars, list) else []


def listing_problems(
    codes: list[str],
    universe_rows: list[dict[str, Any]],
) -> dict[str, Any]:
    """Codes not present in the current universe (suspected delisted/suspended)."""
    universe = {
        str(row.get("code") or "").strip()
        for row in universe_rows
        if str(row.get("code") or "").strip()
    }
    missing = sorted(code for code in codes if code not in universe)
    return {
        "checked": True,
        "universe_count": len(universe),
        "not_in_current_universe": missing,
        "problem": bool(missing),
    }


def history_coverage(
    codes: list[str],
    bars_loader: BarsLoader,
    history_root: Path | str,
) -> dict[str, Any]:
    """Fraction of the watchlist with non-empty daily history."""
    if not codes:
        return {"checked": True, "covered": 0, "total": 0, "missing_codes": [], "problem": False}
    covered: list[str] = []
    missing: list[str] = []
    for code in codes:
        bars = bars_loader(Path(history_root), code)
        (covered if bars else missing).append(code)
    ratio = len(covered) / len(codes)
    return {
        "checked": True,
        "covered": len(covered),
        "total": len(codes),
        "coverage": round(ratio, 4),
        "missing_codes": missing,
        "problem": ratio < MIN_HISTORY_COVERAGE,
    }


def continuity_problems(
    codes: list[str],
    bars_loader: BarsLoader,
    history_root: Path | str,
    *,
    max_gap_days: int = MAX_CALENDAR_GAP_DAYS,
) -> list[dict[str, Any]]:
    """Codes whose daily bars have calendar gaps beyond the threshold."""
    problems: list[dict[str, Any]] = []
    for code in codes:
        bars = bars_loader(Path(history_root), code)
        dates = sorted(
            {str(row.get("date") or "")[:10] for row in bars if row.get("date")}
        )
        if len(dates) < 2:
            continue
        gaps: list[dict[str, Any]] = []
        for previous, current in zip(dates, dates[1:]):
            try:
                gap_days = (date.fromisoformat(current) - date.fromisoformat(previous)).days
            except ValueError:
                continue
            if gap_days > max_gap_days:
                gaps.append({"from": previous, "to": current, "gap_days": gap_days})
        if gaps:
            problems.append({"code": code, "gaps": gaps})
    return problems


def run_quality_audit(
    *,
    watchlist_path: Path | str,
    history_root: Path | str,
    audit_root: Path | str,
    universe_fetcher: UniverseFetcher | None = None,
    watchlist_loader: WatchlistLoader | None = None,
    bars_loader: BarsLoader | None = None,
    now: datetime | None = None,
) -> dict[str, Any]:
    """Run all checks and append the result record (JSONL, one per day)."""
    watchlist_path = Path(watchlist_path)
    watchlist_loader = watchlist_loader or default_watchlist_loader
    bars_loader = bars_loader or default_bars_loader
    current = now or datetime.now()
    codes = _watchlist_codes(watchlist_loader(watchlist_path))

    listing: dict[str, Any] = {"checked": False, "problem": False, "reason": "universe_unavailable"}
    if universe_fetcher is not None:
        try:
            listing = listing_problems(codes, universe_fetcher())
        except Exception as exc:  # noqa: BLE001 - tolerant of upstream failure
            listing = {
                "checked": False,
                "problem": False,
                "reason": f"{type(exc).__name__}: {str(exc)[:120]}",
            }

    coverage = history_coverage(codes, bars_loader, history_root)
    continuity = continuity_problems(codes, bars_loader, history_root)

    problems: list[str] = []
    if listing.get("problem"):
        problems.append(
            "suspected delisted/suspended (not in current universe): "
            + ",".join(listing["not_in_current_universe"][:10])
        )
    if coverage.get("problem"):
        problems.append(f"history coverage {coverage['coverage']} < {MIN_HISTORY_COVERAGE}")
    if continuity:
        problems.append(f"codes with calendar gaps: {len(continuity)}")

    record = {
        "schema_version": "ashare_data_immunity.audit.v1",
        "audit_date": current.date().isoformat(),
        "checked_at": current.isoformat(timespec="seconds"),
        "watchlist_code_count": len(codes),
        "listing": listing,
        "history_coverage": coverage,
        "continuity": continuity,
        "problems": problems,
        "passed": not problems,
    }
    audit_root = Path(audit_root)
    audit_root.mkdir(parents=True, exist_ok=True)
    path = audit_root / f"{record['audit_date']}.jsonl"
    with path.open("a", encoding="utf-8") as handle:
        handle.write(json.dumps(record, ensure_ascii=False, sort_keys=True) + "\n")
    return record
