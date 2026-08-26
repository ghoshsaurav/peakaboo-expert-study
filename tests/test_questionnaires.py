from __future__ import annotations

from src.questionnaires import COMPREHENSION_ITEMS, TERM_HELP, TERM_LABELS


def test_comprehension_items_include_answer_key_explanations() -> None:
    assert len(COMPREHENSION_ITEMS) == 4
    for item in COMPREHENSION_ITEMS:
        assert item["correct"] in item["options"]
        assert item["explanation"].strip()
        assert len(item["options"]) <= 3
        assert item.get("help_terms")


def test_key_terms_have_simple_help_text_and_labels() -> None:
    required = {
        "candidate",
        "chromatogram",
        "detectability",
        "perturbation",
        "stability",
        "parameter_robustness",
        "defer",
        "recommendation",
        "ai_peak_mark",
    }
    assert required.issubset(TERM_HELP)
    assert required.issubset(TERM_LABELS)
    assert all(TERM_HELP[key].strip() for key in required)
    assert all(len(TERM_HELP[key].split()) <= 35 for key in required)
