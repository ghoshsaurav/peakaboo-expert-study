#!/usr/bin/env python3
"""Delete a local SQLite study database and its SQLite sidecar files."""

from __future__ import annotations

import argparse
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]


def main() -> None:
    """Require explicit confirmation and remove the configured local database files."""
    parser = argparse.ArgumentParser(description="Delete the local study database and SQLite sidecar files.")
    parser.add_argument("--database", type=Path, default=ROOT / "data" / "results" / "study_v3.db")
    parser.add_argument("--yes", action="store_true", help="Confirm destructive reset")
    args = parser.parse_args()
    if not args.yes:
        raise SystemExit("Reset cancelled. Re-run with --yes.")
    for suffix in ("", "-wal", "-shm"):
        target = Path(str(args.database) + suffix)
        if target.exists():
            target.unlink()
            print(f"Deleted {target}")


if __name__ == "__main__":
    main()
