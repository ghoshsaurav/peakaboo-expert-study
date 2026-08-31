"""Central definitions for study wording, response choices, help text, and practice items."""

from __future__ import annotations

from typing import Any


# Plain-language definitions shown through clickable ? help controls.
TERM_HELP = {
    "candidate": "The marked bump that the software thinks might be a peak.",
    "peak": "A rise in the signal that may represent a chemical component.",
    "chromatogram": "A line chart showing how the measured signal changes over time.",
    "raw_signal": "The signal exactly as it was measured, before smoothing.",
    "smoothed_signal": "A less jagged version of the signal used to make its overall shape easier to see.",
    "detector": "The software rule that marks possible peaks.",
    "evidence": "Information that may help you judge whether the marked bump should be kept as a peak.",
    "detectability": "How clearly the marked bump rises above nearby noise. A larger value means it stands out more.",
    "prominence": "How much the bump rises above the signal around it.",
    "local_noise": "Small, irregular changes in the signal near the marked bump.",
    "decision_boundary": "The detector's cutoff. A value close to the cutoff can change after a small change in the data.",
    "boundary_margin": "How far the candidate is above or below the detector's cutoff. Near zero means it is close to the cutoff.",
    "perturbation": "A small, realistic change made to the signal to test whether the software gives the same result again.",
    "stability": "How often the software finds the same candidate after those small signal changes. This measures repeatability, not whether the peak is truly real.",
    "parameter": "A software setting, such as smoothing strength or the minimum size needed to mark a peak.",
    "parameter_robustness": "How often the candidate stays detected after small changes to normal software settings.",
    "local_variation_band": "The shaded area showing nearby signal variation. It is not a formal confidence interval.",
    "structural_ambiguity": "A shape problem such as overlap, a shoulder, a duplicate mark, or a changing baseline.",
    "overlap": "Two nearby peaks may partly cover each other, making their shapes difficult to separate.",
    "duplicate": "The software may have marked the same underlying peak more than once.",
    "baseline": "The background level of the signal when no clear peak is present.",
    "provenance": "The software settings and version that produced the candidate.",
    "defer": "Do not accept or reject yet. Send the case for more review.",
    "reference": "A comparison label used in the study. It helps evaluate decisions but is not perfect chemical truth.",
    "recommendation": "The AI's direct advice about what action to take. The advice can be wrong.",
    "ai_peak_mark": "The AI is explicitly saying: this candidate is a peak and should be accepted.",
    "confidence": "How sure you are about your own answer.",
    "evidence_conflict": "Two pieces of information point in different directions.",
    "retention_time": "The time at which a signal feature appears in the chromatogram.",
    "signal_to_noise": "A comparison between the size of a possible peak and nearby noise.",
    "calibration": "How well a person's confidence matches how often their decisions agree with the study reference.",
}

TERM_LABELS = {
    "candidate": "Candidate",
    "peak": "Peak",
    "chromatogram": "Chromatogram",
    "raw_signal": "Raw signal",
    "smoothed_signal": "Smoothed signal",
    "detector": "Peak detector",
    "evidence": "Evidence",
    "detectability": "How clearly it stands out",
    "prominence": "Prominence",
    "local_noise": "Nearby noise",
    "decision_boundary": "Detector cutoff",
    "boundary_margin": "Distance from cutoff",
    "perturbation": "Small signal change",
    "stability": "Repeatability after signal changes",
    "parameter": "Software setting",
    "parameter_robustness": "Repeatability after setting changes",
    "local_variation_band": "Local variation band",
    "structural_ambiguity": "Shape uncertainty",
    "overlap": "Overlapping peaks",
    "duplicate": "Duplicate mark",
    "baseline": "Baseline",
    "provenance": "Processing details",
    "defer": "Defer",
    "reference": "Study reference",
    "recommendation": "AI recommendation",
    "ai_peak_mark": "AI marks this as a peak",
    "confidence": "Confidence",
    "evidence_conflict": "Conflicting evidence",
    "retention_time": "Retention time",
    "signal_to_noise": "Signal-to-noise",
    "calibration": "Confidence calibration",
}

DECISION_OPTIONS = {
    "Accept as a peak.": 1,
    "Reject as noise, an error, or a duplicate.": 2,
    "Defer for more review.": 3,
}

BASELINE_EVIDENCE_OPTIONS = [
    "Peak shape",
    "How strong the signal looks",
    "Nearby noise or baseline",
    "Nearby or overlapping peak",
    "Not enough information",
]

PEAKABOO_EVIDENCE_OPTIONS = [
    "Peak shape",
    "How clearly it stands out",
    "Repeatability after signal changes",
    "Repeatability after setting changes",
    "Nearby noise or shaded band",
    "Overlap or duplicate warning",
    "Not enough information",
]

EXPLANATION_OPTIONS = [
    "Weak compared with nearby noise",
    "Close to the detector cutoff",
    "Changes after small signal changes",
    "Changes after small setting changes",
    "Possible overlap or duplicate",
    "The evidence points in different directions",
]

ROLE_OPTIONS = [
    "Lab scientist or analyst",
    "Method or quality-control specialist",
    "Researcher or faculty member",
    "Student or trainee",
    "Other",
]

EXPERIENCE_OPTIONS = [
    "Less than 1 year",
    "1–3 years",
    "4–7 years",
    "More than 7 years",
]

REVIEW_FREQUENCY_OPTIONS = [
    "Daily or several times per week",
    "Weekly",
    "Monthly",
    "Less than monthly",
]

CURRENT_PRACTICE_EVIDENCE = [
    "Peak shape",
    "How clearly it rises above noise",
    "Nearby noise or baseline",
    "Nearby or overlapping peaks",
    "Expected time or chemical knowledge",
    "Comparison with other runs",
]

DEFERRAL_REASONS = [
    "Weak or noisy signal",
    "Overlap or baseline problem",
    "Information points in different directions",
    "A second reviewer is needed",
    "I rarely defer",
]

ERROR_COST_OPTIONS = [
    "Missing a real peak",
    "Accepting a false peak",
    "Both are about equally costly",
    "It depends on the task",
]

DISTRUST_OPTIONS = [
    "It misses weak peaks",
    "It marks false or duplicate peaks",
    "The result changes after small setting changes",
    "It gives too little explanation",
    "It conflicts with my knowledge",
]

LIKERT_5 = list(range(1, 6))

COMPREHENSION_ITEMS = [
    {
        "code": "stability_correctness",
        "prompt": "If the software repeatedly finds a candidate after small signal changes, it must be a real chemical peak.",
        "options": ["True", "False", "Unsure"],
        "correct": "False",
        "explanation": "Repeatability only means the software gives the same result again. A repeatable result can still be wrong or unsupported.",
        "help_terms": ["perturbation", "stability", "peak"],
    },
    {
        "code": "margin_meaning",
        "prompt": "What does a value close to the detector cutoff mean?",
        "options": [
            "A small change could change the detector's result",
            "The candidate is definitely noise",
            "The candidate is always stable",
        ],
        "correct": "A small change could change the detector's result",
        "explanation": "A value close to the cutoff is borderline. Small changes in the signal or settings may change whether it is detected.",
        "help_terms": ["decision_boundary", "boundary_margin"],
    },
    {
        "code": "perturbation_meaning",
        "prompt": "What does repeatability after small signal changes measure?",
        "options": [
            "Whether the software finds the candidate again",
            "The chemical identity",
            "The exact peak area",
        ],
        "correct": "Whether the software finds the candidate again",
        "explanation": "The signal is changed slightly many times, and the study counts how often the candidate is found again.",
        "help_terms": ["perturbation", "stability"],
    },
    {
        "code": "conflict_action",
        "prompt": "What is a reasonable action when the information points in different directions?",
        "options": [
            "Review the conflict and consider deferring",
            "Always accept the software output",
            "Always reject the candidate",
        ],
        "correct": "Review the conflict and consider deferring",
        "explanation": "Conflicting information means the case may need closer review. Deferring is a valid choice.",
        "help_terms": ["evidence_conflict", "defer"],
    },
]

POST_CONDITION_ITEMS = [
    ("usefulness", "This view helped me make the decision."),
    ("clarity", "The information was easy to understand."),
    ("mental_effort", "This view required a lot of effort to understand."),
    ("appropriate_reliance", "This view helped me decide when to trust the software."),
]

FINAL_CONDITION_LABELS = {
    "baseline": "1. Signal-only view",
    "peakaboo": "2. Separate-evidence view",
    "peakaboo_recommendation": "3. AI-marks-it-as-a-peak view",
}


def machine_code(label: str) -> str:
    """Convert a human-readable response label into a stable machine-friendly code."""
    return (
        label.strip()
        .lower()
        .replace("–", "-")
        .replace("/", "_")
        .replace(" ", "_")
        .replace(".", "")
        .replace(",", "")
        .replace("'", "")
        .replace("(", "")
        .replace(")", "")
    )
