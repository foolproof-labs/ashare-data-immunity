# ashare-data-immunity

**Data immunity for A-share daily bars**: cleaning (NaN / OHLCV
validation), board-aware price-limit and suspension detection, quality
audit (listing / coverage / continuity) and snapshot versioning (sha256
manifests). Python 3.11+, **zero dependencies**, Windows / Linux / macOS.

**Status:** v0.1 —alpha. The audit structure is distilled from a
production A-share pipeline; board rules follow the current exchange
conventions and should be re-checked against the exchanges' rule
documents before you rely on them.

## Why this exists

A-share daily data is not born clean. Vendors ship NaN closes, negative
opens, volume in lots or shares depending on the board, silent suspensions
that look like flat prices, and limit-up days that look like "huge moves"
unless you know the board's 10/20/30% rule. Every one of these corrupts a
factor pipeline differently, and most corrupt it *quietly*.

`ashare-data-immunity` is the immune system: it does not fetch data and it
does not trade —it makes the data you already have **honest**:

- **clean** —flag or sanitize non-finite values, non-positive prices,
  OHLC inconsistencies (high below max(open, close), low above
  min(open, close)), negative volume;
- **limits** —board-aware price-limit detection (main ±10%, STAR and
  ChiNext ±20%, BSE ±30%, ST ±5% on the main board) against the previous
  close with tick rounding tolerance, plus a documented suspension
  heuristic (zero volume, or no prices on a dated row);
- **audit** —daily quality audit: are watched codes still listed, does
  history coverage meet the threshold, are there calendar gaps? All data
  sources injectable, results append-only;
- **snapshot** —sha256 manifests with cutoffs, so "which data did this
  backtest actually see" is a file you can compare and prove.

## Philosophy

**Data is an asset; immunity is a discipline.**

Most data tooling optimizes for *getting* data. This tool optimizes for
*trusting* the data you have —and it refuses to guess: board rules are
explicit tables, the suspension detector is documented as a heuristic
(vendor conventions differ), and the audit reports "universe unavailable"
instead of pretending the listing check ran. Read-only by design; every
function either returns a report or writes an append-only record. Nothing
here trades, prices, or decides.

## Quick start

```bash
# install from PyPI (once published)
pip install ashare-data-immunity

# or run without installing anything:
#   PYTHONPATH=src python -m ashare_data_immunity --help

python examples/demo.py   # clean + limits + audit + snapshot on synthetic data
```

Your own data:

```bash
# 1. validate / clean a bars file
imm clean --bars bars.json                     # exit 1 when problems found
imm clean --bars bars.json --drop-non-positive --out clean.json

# 2. board-aware limits + suspensions
imm limits --bars bars.json --code 600000
imm limits --bars bars.json --code 688001 --st

# 3. daily quality audit (watchlist + history dir + append-only audit dir)
imm audit --watchlist watchlist.json \
  --history-root data/daily --audit-root data/audits

# 4. snapshot versioning
imm snapshot --name v2026-08-01 --cutoff 2026-08-01 \
  --files data/daily/*.json --root data --out manifests/v1.json
imm snapshot-compare --before manifests/v1.json --after manifests/v2.json
```

## Commands

| Command | What it does |
| --- | --- |
| `clean` | Validate bars (missing/non-finite/non-positive fields, OHLC consistency, negative volume); optionally sanitize (non-finite and non-positive prices →?`None`, volume kept ≥0) and optionally drop non-positive rows |
| `limits` | Board classification, price-limit events (up/down with ratio and limit price) and suspension days for one code |
| `audit` | Listing (codes not in the injected universe), history coverage, calendar continuity; appends a JSONL record per day |
| `snapshot` | sha256 manifest of a file list with name + cutoff |
| `snapshot-compare` | added / removed / changed files between two manifests |
| `version` | Print version |

## Board rules (v0.1)

| Board | Prefixes | Limit |
| --- | --- | --- |
| main | 60xxxx / 00xxxx | ±10% (ST: ±5%) |
| STAR | 688 / 689 | ±20% |
| ChiNext | 300 / 301 | ±20% |
| Beijing SE | 43x / 83x / 87x / 920 | ±30% |
| unknown | —| ±10% (assumed main) |

Limit detection compares `close` against `round(prev_close × (1 ± ratio), 2)`
with a default tolerance of 0.001 for vendor rounding conventions. The
first bar has no reference and is never flagged. **Verify the tables
against the current exchange rule documents before production use** —the
tool's job is to make the rules explicit, not to invent them.

Suspension heuristic: a dated row with zero volume, or with no prices at
all, is a suspension day. Documented, not hidden —and toggleable
(`zero_volume_means_suspended`).

## Development

```bash
python -m pip install -e . pytest
python -m pytest
```

CI runs the full test suite on Ubuntu, Windows and macOS with Python 3.11
and 3.12. Issues are handled on weekends; pull requests are welcome.

## Related work

This tool makes no claims to novelty of its own: it is the engineering
layer under the data-quality principles that the industry is converging on
—point-in-time discipline ([Kelly et al., NBER w35247](https://www.nber.org/papers/w35247)),
look-ahead awareness ([Fonseca 2026, arXiv:2607.04958](https://econpapers.repec.org/paper/arxpapers/2607.04958.htm))
and reproducible snapshots. The pieces that *are* worth citing live in the
sibling repos of this project family; this one just keeps the data honest.

## Project family

Part of [Foolproof Labs](https://github.com/foolproof-labs) — a toolchain
against self-deception in quantitative research:

- [pit-adjuster](https://github.com/foolproof-labs/pit-adjuster) — PIT back-adjustment with static forward-adjustment drift detection
- [falsification-ledger](https://github.com/foolproof-labs/falsification-ledger) — pre-registration and falsification ledger
- [factor-qc](https://github.com/foolproof-labs/factor-qc) — fail-closed backtest quality gate
- [lesson-book](https://github.com/foolproof-labs/lesson-book) — tuition memory for traders
- [lookahead-free](https://github.com/foolproof-labs/lookahead-free) — verifiable look-ahead-freedom checks
- [ashare-data-immunity](https://github.com/foolproof-labs/ashare-data-immunity) — data immunity for A-share daily bars

## License

MIT
