#!/usr/bin/env python3
"""Create a local demonstration database with simulated study responses.

The generated records are for software testing and figure development only; they
are not human-subject study findings.
"""

from __future__ import annotations

import argparse
import random
import sys
from pathlib import Path

import pandas as pd

ROOT = Path(__file__).resolve().parents[1]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

from src.assignment import assign_cases, condition_order  # noqa: E402
from src.logging_store import StudyStore  # noqa: E402


def main() -> None:
    """Reset the demo database and populate it with deterministic simulated participants."""
    parser = argparse.ArgumentParser(description="Create a demonstration database with simulated responses.")
    parser.add_argument("--database", type=Path, default=ROOT / "data" / "demo" / "demo_study.db")
    parser.add_argument("--case-bank", type=Path, default=ROOT / "data" / "demo" / "case_bank.csv")
    parser.add_argument("--participants", type=int, default=12)
    args = parser.parse_args()
    for suffix in ("", "-wal", "-shm"):
        target = Path(str(args.database) + suffix)
        if target.exists():
            target.unlink()

    bank = pd.read_csv(args.case_bank)
    store = StudyStore(args.database)
    conditions = ["baseline", "peakaboo", "peakaboo_recommendation"]
    rng = random.Random(20260805)

    for participant_number in range(1, args.participants + 1):
        participant_id = f"DEMO{participant_number:03d}"
        order = condition_order(participant_id, conditions, 20260805)
        session_id = store.get_or_create_session(participant_id, ">".join(order), "demo-48-v3", "3.0.0-demo")
        assignment = assign_cases(
            bank,
            participant_id,
            conditions,
            total_trials=9,
            global_seed=20260805,
            trials_per_condition=3,
        )
        store.save_assignments(session_id, assignment)
        store.save_survey_response(session_id, "background", "role", "analytical_scientist", "Analytical scientist")
        store.save_survey_response(session_id, "background", "completed", "yes", "yes")
        store.save_survey_response(session_id, "current_practice", "completed", "yes", "yes")
        store.save_survey_response(session_id, "comprehension", "score", "4", "4/4", {"score": 4, "total": 4})
        store.save_survey_response(session_id, "comprehension", "completed", "yes", "yes")

        for _, row in assignment.iterrows():
            status = str(row["hidden_reference_status"])
            condition = str(row["condition"])
            recommendation = str(row.get("displayed_recommendation") or "Accept")
            reference_decision = 1 if status == "supported" else 2

            if condition == "baseline":
                decision = reference_decision if rng.random() > 0.28 else rng.choice([1, 2, 3])
                evidence = rng.choice(["Peak shape", "Signal strength", "Local noise or baseline"])
                shown_recommendation = None
            elif condition == "peakaboo":
                decision = reference_decision if rng.random() > 0.18 else rng.choice([1, 2, 3])
                evidence = rng.choice(
                    ["How clearly it stands out", "Repeatability after signal changes", "Repeatability after setting changes", "Overlap or duplicate warning"]
                )
                shown_recommendation = None
            else:
                rec_code = {"Accept": 1, "Reject": 2, "Defer": 3}[recommendation]
                # Simulate some recommendation following, including incorrect recommendations.
                decision = rec_code if rng.random() < 0.68 else reference_decision
                evidence = rng.choice(["AI says this is a peak", "How clearly it stands out", "Repeatability after signal changes"])
                shown_recommendation = recommendation

            label = {
                1: "Accept as a peak.",
                2: "Reject as noise, an error, or a duplicate.",
                3: "Defer for more review.",
            }[decision]
            followed = None
            if shown_recommendation:
                followed = int(decision == {"Accept": 1, "Reject": 2, "Defer": 3}[shown_recommendation])

            store.save_trial_response(
                {
                    "session_id": session_id,
                    "trial_id": row["trial_id"],
                    "case_id": row["case_id"],
                    "condition": condition,
                    "decision_code": decision,
                    "decision_label": label,
                    "confidence": rng.randint(45, 95),
                    "selected_evidence": [evidence],
                    "primary_evidence": evidence,
                    "recommendation": shown_recommendation,
                    "recommendation_followed": followed,
                    "response_time_seconds": rng.uniform(12, 55),
                    "evidence_disagreement": "Yes" if row["hidden_disagreement_type"] != "none" else "No",
                    "clarity": rng.randint(2, 5) if condition != "baseline" else None,
                }
            )
        for condition in conditions:
            for code, value in {
                "usefulness": rng.randint(3, 5),
                "clarity": rng.randint(2, 5),
                "mental_effort": rng.randint(2, 5),
                "appropriate_reliance": rng.randint(2, 5),
            }.items():
                store.save_survey_response(session_id, f"post_{condition}", code, value, value)
            store.save_survey_response(session_id, f"post_{condition}", "completed", "yes", "yes")
        store.save_survey_response(session_id, "final", "completed", "yes", "yes")
        store.complete_session(session_id)
    print(f"Created demonstration database: {args.database}")


if __name__ == "__main__":
    main()
