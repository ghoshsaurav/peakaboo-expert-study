#!/usr/bin/env python3
from __future__ import annotations

import argparse
import shutil
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]


def main() -> None:
    parser = argparse.ArgumentParser(description="Copy the bundled demonstration database into the active results path.")
    parser.add_argument("--source", type=Path, default=ROOT / "data" / "demo" / "demo_study.db")
    parser.add_argument("--target", type=Path, default=ROOT / "data" / "results" / "study_v3.db")
    parser.add_argument("--yes", action="store_true")
    args = parser.parse_args()
    if not args.yes:
        raise SystemExit("Copy cancelled. Re-run with --yes.")
    args.target.parent.mkdir(parents=True, exist_ok=True)
    shutil.copy2(args.source, args.target)
    print(f"Copied {args.source} to {args.target}")


if __name__ == "__main__":
    main()
