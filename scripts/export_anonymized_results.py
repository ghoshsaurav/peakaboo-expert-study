#!/usr/bin/env python3
"""Export study tables with participant IDs replaced by salted pseudonyms."""

from __future__ import annotations

import argparse
import hashlib
import sys
from pathlib import Path

import pandas as pd

ROOT = Path(__file__).resolve().parents[1]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

from src.config import load_config, resolve_paths  # noqa: E402
from src.logging_store import StudyStore  # noqa: E402
from src.metrics import analysis_ready_trials  # noqa: E402


def pseudonym(value: str, salt: str) -> str:
    """Create a stable short participant code from an ID and caller-provided salt."""
    return "P-" + hashlib.sha256(f"{salt}|{value}".encode("utf-8")).hexdigest()[:10]


def main() -> None:
    """Load study tables, remove participant IDs, and write anonymized CSV exports."""
    parser = argparse.ArgumentParser()
    parser.add_argument("--database", type=Path)
    parser.add_argument("--output-dir", type=Path, default=ROOT / "data" / "exports")
    parser.add_argument("--salt", default="replace-before-sharing")
    args = parser.parse_args()

    config = load_config()
    paths = resolve_paths(config)
    database = args.database or paths.database
    store = StudyStore(database)
    args.output_dir.mkdir(parents=True, exist_ok=True)

    sessions = store.table("sessions")
    assignments = store.table("assignments")
    trials = store.table("trial_responses")
    surveys = store.table("survey_responses")
    analysis = analysis_ready_trials(assignments, trials)

    if not sessions.empty:
        participant_map = {
            row["session_id"]: pseudonym(str(row["participant_id"]), args.salt)
            for _, row in sessions.iterrows()
        }
        sessions["participant_code"] = sessions["session_id"].map(participant_map)
        sessions = sessions.drop(columns=["participant_id"], errors="ignore")
        for frame in (assignments, trials, surveys, analysis):
            if not frame.empty and "session_id" in frame:
                frame["participant_code"] = frame["session_id"].map(participant_map)

    sessions.to_csv(args.output_dir / "sessions_anonymized.csv", index=False)
    assignments.to_csv(args.output_dir / "assignments_anonymized.csv", index=False)
    trials.to_csv(args.output_dir / "trial_responses_anonymized.csv", index=False)
    surveys.to_csv(args.output_dir / "survey_responses_anonymized.csv", index=False)
    analysis.to_csv(args.output_dir / "analysis_ready_trials_anonymized.csv", index=False)
    print(f"Exports written to {args.output_dir}")


if __name__ == "__main__":
    main()
