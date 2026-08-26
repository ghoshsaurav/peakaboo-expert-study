from __future__ import annotations

from pathlib import Path

import pandas as pd

from src.assignment import assign_cases, condition_order


ROOT = Path(__file__).resolve().parents[1]
BANK = pd.read_csv(ROOT / "data" / "demo" / "case_bank.csv")
CONDITIONS = ["baseline", "peakaboo", "peakaboo_recommendation"]


def test_assignment_has_three_shared_cases_and_three_per_condition() -> None:
    assignment = assign_cases(
        BANK,
        "P001",
        CONDITIONS,
        total_trials=9,
        trials_per_condition=3,
        global_seed=20260805,
    )
    assert len(assignment) == 9
    assert assignment["case_id"].nunique() == 3
    assert assignment["pair_id"].nunique() == 3
    assert assignment["condition"].value_counts().to_dict() == {
        "baseline": 3,
        "peakaboo": 3,
        "peakaboo_recommendation": 3,
    }
    assert assignment.groupby("case_slot")["case_id"].nunique().eq(1).all()
    assert assignment.groupby("case_slot").size().eq(3).all()


def test_fixed_condition_order() -> None:
    expected = ["baseline", "peakaboo", "peakaboo_recommendation"]
    assert condition_order("P001", CONDITIONS, 20260805) == expected
    assert condition_order("P999", CONDITIONS, 20260805) == expected


def test_same_case_order_in_all_three_conditions() -> None:
    assignment = assign_cases(BANK, "P003", CONDITIONS, 9, 20260805, 3)
    baseline = assignment[assignment["condition"] == "baseline"].sort_values("case_slot")["case_id"].tolist()
    evidence = assignment[assignment["condition"] == "peakaboo"].sort_values("case_slot")["case_id"].tolist()
    recommendation = assignment[assignment["condition"] == "peakaboo_recommendation"].sort_values("case_slot")["case_id"].tolist()
    assert baseline == evidence == recommendation


def test_selected_cases_are_challenging_not_clear() -> None:
    assignment = assign_cases(BANK, "P004", CONDITIONS, 9, 20260805, 3)
    unique_cases = assignment.drop_duplicates("case_id")
    assert not unique_cases["hidden_case_category"].astype(str).str.startswith("clear_").any()


def test_recommendation_condition_explicitly_marks_peak() -> None:
    assignment = assign_cases(BANK, "P005", CONDITIONS, 9, 20260805, 3)
    rec = assignment[assignment["condition"] == "peakaboo_recommendation"]
    assert set(rec["displayed_recommendation"]) == {"Accept"}


def test_assignment_is_reproducible() -> None:
    first = assign_cases(BANK, "P003", CONDITIONS, 9, 20260805, 3)
    second = assign_cases(BANK, "P003", CONDITIONS, 9, 20260805, 3)
    assert first[["case_id", "condition", "case_slot", "trial_position"]].equals(
        second[["case_id", "condition", "case_slot", "trial_position"]]
    )


def test_total_must_match_three_per_condition() -> None:
    try:
        assign_cases(BANK, "P001", CONDITIONS, 12, 20260805, 3)
    except ValueError as exc:
        assert "total_trials" in str(exc)
    else:
        raise AssertionError("Expected invalid total to raise ValueError")
