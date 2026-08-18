"""Snapshot versioning: sha256 manifests and equivalence checks.

A data snapshot is a named collection of files with a cutoff.  ``build_snapshot``
writes a manifest (path -> sha256, plus cutoff and built-at time); ``compare_snapshots``
reports added / removed / changed files between two snapshots — the
reproducibility gate for data pipelines and migrations.
"""

from __future__ import annotations

import hashlib
import json
from datetime import datetime
from pathlib import Path
from typing import Any

MANIFEST_SCHEMA = "ashare_data_immunity.snapshot_manifest.v1"


def _file_sha256(path: Path) -> str:
    digest = hashlib.sha256()
    with path.open("rb") as handle:
        for chunk in iter(lambda: handle.read(65536), b""):
            digest.update(chunk)
    return digest.hexdigest()


def build_snapshot(
    files: list[Path | str],
    *,
    name: str,
    cutoff: str,
    out_path: Path | str | None = None,
    root: Path | str | None = None,
) -> dict[str, Any]:
    """Hash a list of files into a manifest.

    ``root`` (when given) is stripped from stored paths so manifests are
    relocatable.  ``out_path`` writes the manifest JSON.
    """
    root_path = Path(root) if root is not None else None
    entries: dict[str, str] = {}
    missing: list[str] = []
    for item in files:
        path = Path(item)
        if not path.is_file():
            missing.append(str(item))
            continue
        key = str(path.relative_to(root_path)) if root_path else str(path)
        entries[key] = _file_sha256(path)
    manifest = {
        "schema_version": MANIFEST_SCHEMA,
        "name": name,
        "cutoff": cutoff,
        "built_at": datetime.now().astimezone().isoformat(timespec="seconds"),
        "file_count": len(entries),
        "files": entries,
        "missing": missing,
    }
    if out_path is not None:
        target = Path(out_path)
        target.parent.mkdir(parents=True, exist_ok=True)
        target.write_text(json.dumps(manifest, ensure_ascii=False, indent=2), encoding="utf-8")
    return manifest


def compare_snapshots(
    before: dict[str, Any],
    after: dict[str, Any],
) -> dict[str, Any]:
    """Compare two manifests: added / removed / changed files.

    Returns ``{"equal": bool, "added": [...], "removed": [...], "changed": [...]}``.
    """
    before_files = before.get("files") or {}
    after_files = after.get("files") or {}
    added = sorted(set(after_files) - set(before_files))
    removed = sorted(set(before_files) - set(after_files))
    changed = sorted(
        path
        for path in set(before_files) & set(after_files)
        if before_files[path] != after_files[path]
    )
    return {
        "equal": not added and not removed and not changed,
        "added": added,
        "removed": removed,
        "changed": changed,
    }
