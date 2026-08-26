from __future__ import annotations

from pathlib import Path

import pandas as pd

from src.logging_store import StudyStore
from src.metrics import analysis_ready_trials


def test_structured_trial_logging_and_reliance_category(tmp_path: Path) -> None:
    store = StudyStore(tmp_path / "study.db")
    session_id = store.get_or_create_session("P001", "baseline>peakaboo>peakaboo_recommendation", "test", "2.0")
    assignment = pd.DataFrame(
        [
            {
                "trial_id": "P001-001",
                "case_id": "SYN-001",
                "pair_id": "SYN-PAIR-01",
                "condition": "peakaboo_recommendation",
                "block_number": 1,
                "trial_position": 1,
                "source_type": "synthetic",
                "hidden_case_category": "stable_unsupported",
                "hidden_disagreement_type": "favorable_algorithm_vs_unsupported_reference",
                "hidden_reference_status": "unsupported",
                "algorithmic_recommendation": "Accept",
            }
        ]
    )
    store.save_assignments(session_id, assignment)
    store.save_trial_response(
        {
            "session_id": session_id,
            "trial_id": "P001-001",
            "case_id": "SYN-001",
            "condition": "peakaboo_recommendation",
            "decision_code": 1,
            "decision_label": "Accept as a peak.",
            "confidence": 90,
            "selected_evidence": ["Algorithmic recommendation"],
            "primary_evidence": "Algorithmic recommendation",
            "recommendation": "Accept",
            "recommendation_followed": 1,
            "response_time_seconds": 12.5,
        }
    )
    trials = analysis_ready_trials(store.table("assignments"), store.table("trial_responses"))
    assert int(trials.loc[0, "used_algorithmic_recommendation"]) == 1
    assert int(trials.loc[0, "unsupported_accept"]) == 1
    assert trials.loc[0, "reliance_category"] == "over_reliance"
    assert float(trials.loc[0, "calibration_error"]) == 0.9
