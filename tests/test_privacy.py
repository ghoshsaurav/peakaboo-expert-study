from __future__ import annotations

from src.models import HIDDEN_CASE_FIELDS, participant_case


def test_participant_case_removes_hidden_labels() -> None:
    case = {
        "case_id": "X",
        "detectability": 12.0,
        "hidden_reference_status": "unsupported",
        "hidden_case_category": "stable_unsupported",
        "hidden_disagreement_type": "favorable_algorithm_vs_unsupported_reference",
        "reference_interval_start": 1.0,
        "reference_interval_end": 2.0,
        "algorithmic_recommendation": "Reject",
    }
    safe = participant_case(case)
    assert safe["case_id"] == "X"
    assert safe["detectability"] == 12.0
    assert HIDDEN_CASE_FIELDS.isdisjoint(safe)
