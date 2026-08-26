#!/usr/bin/env python3
from __future__ import annotations

import argparse
import sys
from pathlib import Path

import numpy as np
import pandas as pd

ROOT = Path(__file__).resolve().parents[1]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

from src.data_loader import load_signal_bundle  # noqa: E402


def validate(case_bank: Path, signals: Path) -> list[str]:
    errors: list[str] = []
    frame = pd.read_csv(case_bank)
    required = {
        "case_id",
        "pair_id",
        "source_type",
        "signal_key",
        "candidate_time",
        "hidden_reference_status",
        "hidden_case_category",
        "hidden_disagreement_type",
        "detectability",
        "stability",
        "parameter_robustness",
        "pilot_ready",
    }
    missing = sorted(required - set(frame.columns))
    if missing:
        errors.append(f"Missing columns: {missing}")
        return errors
    if frame["case_id"].duplicated().any():
        errors.append("Duplicate case IDs")
    pair_sizes = frame.groupby("pair_id").size()
    bad_pairs = pair_sizes[pair_sizes != 2]
    if not bad_pairs.empty:
        errors.append(f"Pairs not containing exactly two cases: {bad_pairs.to_dict()}")
    if set(frame["source_type"]) != {"real", "synthetic"}:
        errors.append("Both real and synthetic sources are required")
    if not frame["detectability"].replace([np.inf, -np.inf], np.nan).notna().all():
        errors.append("Non-finite detectability values")
    if not frame["stability"].between(0, 1).all():
        errors.append("Stability values outside [0,1]")
    if not frame["parameter_robustness"].between(0, 1).all():
        errors.append("Parameter robustness values outside [0,1]")

    for _, row in frame.iterrows():
        try:
            bundle = load_signal_bundle(signals, str(row["signal_key"]))
        except Exception as exc:  # pragma: no cover - diagnostic script
            errors.append(f"{row['case_id']}: {exc}")
            continue
        lengths = {len(bundle.time), len(bundle.raw), len(bundle.smooth), len(bundle.sigma), len(bundle.lower), len(bundle.upper)}
        if len(lengths) != 1:
            errors.append(f"{row['case_id']}: signal arrays have inconsistent lengths")
        if not 0 <= bundle.candidate_index < len(bundle.time):
            errors.append(f"{row['case_id']}: candidate index is out of range")
        if abs(bundle.time[bundle.candidate_index] - float(row["candidate_time"])) > 1e-6:
            errors.append(f"{row['case_id']}: candidate time does not match signal archive")
    return errors


def main() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument("--case-bank", type=Path, default=ROOT / "data" / "demo" / "case_bank.csv")
    parser.add_argument("--signals", type=Path, default=ROOT / "data" / "demo" / "signals.npz")
    args = parser.parse_args()
    errors = validate(args.case_bank, args.signals)
    if errors:
        print("Case-bank validation failed:")
        for error in errors:
            print(f"- {error}")
        raise SystemExit(1)
    print("Case-bank validation passed.")


if __name__ == "__main__":
    main()
