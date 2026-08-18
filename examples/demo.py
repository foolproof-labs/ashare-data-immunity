"""End-to-end demo: clean -> limits -> audit -> snapshot on synthetic data.

Run with:  python examples/demo.py
Writes fixtures under a temporary directory; safe to re-run.
"""

from __future__ import annotations

import json
import sys
import tempfile
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "src"))

from ashare_data_immunity.cli import main as cli_main  # noqa: E402

TMP = Path(tempfile.mkdtemp(prefix="imm-demo-"))


def _run(label: str, argv: list[str]) -> None:
    print(f"\n== {label} ==")
    code = cli_main(argv)
    print(f"=> exit code: {code}")


def main() -> int:
    # synthetic history for two codes: one clean, one with problems
    bars_600000 = [
        {"date": "2026-08-03", "open": 10.00, "high": 10.20, "low": 9.90, "close": 10.00, "volume": 1200000},
        {"date": "2026-08-04", "open": 10.50, "high": 11.00, "low": 10.40, "close": 11.00, "volume": 1500000},  # limit up
        {"date": "2026-08-05", "open": 11.50, "high": 11.60, "low": 11.20, "close": 11.50, "volume": 900000},
    ]
    bars_688001 = [
        {"date": "2026-08-03", "open": 20.00, "high": 20.50, "low": 19.80, "close": 20.00, "volume": 500000},
        {"date": "2026-08-04", "open": None, "high": None, "low": None, "close": None, "volume": 0},  # suspended
        {"date": "2026-08-05", "open": 24.00, "high": 24.20, "low": 23.80, "close": 24.00, "volume": float("nan")},
    ]

    history_root = TMP / "daily"
    history_root.mkdir()
    (history_root / "600000.json").write_text(json.dumps({"bars": bars_600000}), encoding="utf-8")
    (history_root / "688001.json").write_text(json.dumps({"bars": bars_688001}), encoding="utf-8")
    # clean/limits operate on bare bar lists (audit uses the {"bars": [...]} wrapper)
    bare_600000 = TMP / "600000_bars.json"
    bare_688001 = TMP / "688001_bars.json"
    bare_600000.write_text(json.dumps(bars_600000), encoding="utf-8")
    bare_688001.write_text(json.dumps(bars_688001), encoding="utf-8")

    watchlist = TMP / "watchlist.json"
    watchlist.write_text(json.dumps({"eligible_codes": ["600000", "688001"]}), encoding="utf-8")

    _run("1. clean check (should find nothing wrong)", ["clean", "--bars", str(bare_600000)])
    _run("2. limits for 600000 (limit up on 08-04)", ["limits", "--bars", str(bare_600000), "--code", "600000"])
    _run(
        "3. limits for 688001 (suspension on 08-04)",
        ["limits", "--bars", str(bare_688001), "--code", "688001"],
    )
    _run(
        "4. quality audit",
        ["audit", "--watchlist", str(watchlist), "--history-root", str(history_root),
         "--audit-root", str(TMP / "audits")],
    )
    _run(
        "5. snapshot",
        ["snapshot", "--name", "v1", "--cutoff", "2026-08-05",
         "--files", str(history_root / "600000.json"), str(history_root / "688001.json"),
         "--root", str(history_root), "--out", str(TMP / "manifest.json")],
    )
    _run(
        "6. snapshot-compare (identical)",
        ["snapshot-compare", "--before", str(TMP / "manifest.json"), "--after", str(TMP / "manifest.json")],
    )

    print(f"\nfixtures under: {TMP}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
