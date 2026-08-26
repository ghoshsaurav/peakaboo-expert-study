from __future__ import annotations

import pandas as pd

from src.metrics import same_case_decision_changes


def test_same_case_decision_changes_pivots_three_conditions() -> None:
    trials = pd.DataFrame(
        [
            {"session_id": "S1", "case_id": "C1", "case_slot": 1, "condition": "baseline", "decision_code": 2, "confidence": 60, "hidden_reference_status": "supported", "hidden_case_category": "near_boundary_supported", "hidden_disagreement_type": "detectability_vs_stability"},
            {"session_id": "S1", "case_id": "C1", "case_slot": 1, "condition": "peakaboo", "decision_code": 3, "confidence": 55, "hidden_reference_status": "supported", "hidden_case_category": "near_boundary_supported", "hidden_disagreement_type": "detectability_vs_stability"},
            {"session_id": "S1", "case_id": "C1", "case_slot": 1, "condition": "peakaboo_recommendation", "decision_code": 1, "confidence": 80, "hidden_reference_status": "supported", "hidden_case_category": "near_boundary_supported", "hidden_disagreement_type": "detectability_vs_stability"},
        ]
    )
    result = same_case_decision_changes(trials)
    assert len(result) == 1
    row = result.iloc[0]
    assert row["decision_baseline"] == 2
    assert row["decision_peakaboo"] == 3
    assert row["decision_peakaboo_recommendation"] == 1
    assert row["changed_after_evidence"] == 1
    assert row["changed_after_ai_peak_mark"] == 1
