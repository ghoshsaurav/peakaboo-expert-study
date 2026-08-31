"""Shared study data structures and participant-safety helpers."""

from __future__ import annotations

from dataclasses import dataclass
from typing import Any

import numpy as np


HIDDEN_CASE_FIELDS = {
    "hidden_reference_status",
    "hidden_case_category",
    "hidden_disagreement_type",
    "hidden_expected_recommendation",
    "reference_interval_start",
    "reference_interval_end",
    "reference_interval_id",
    "is_correct_recommendation",
    "algorithmic_recommendation",
}


@dataclass
class SignalBundle:
    """Store the signal window and precomputed evidence arrays for one study case."""

    time: np.ndarray
    raw: np.ndarray
    smooth: np.ndarray
    sigma: np.ndarray
    lower: np.ndarray
    upper: np.ndarray
    candidate_index: int
    nearby_peak_indices: np.ndarray
    stability_hits: np.ndarray
    stability_offsets: np.ndarray
    parameter_matrix: np.ndarray
    parameter_smoothing: np.ndarray
    parameter_k: np.ndarray


def participant_case(case: dict[str, Any]) -> dict[str, Any]:
    """Return a participant-safe copy of a case record with hidden comparison fields removed."""
    return {key: value for key, value in case.items() if key not in HIDDEN_CASE_FIELDS}
