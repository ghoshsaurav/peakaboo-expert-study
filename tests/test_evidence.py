from __future__ import annotations

import numpy as np

from src.evidence import (
    DetectorConfig,
    detectability,
    evidence_agreement,
    moving_average,
    parameter_robustness,
    preprocess_signal,
    weber_margin,
)


def test_detectability_and_margin() -> None:
    score = detectability(0.032, 0.002)
    assert np.isclose(score, 16.0)
    assert np.isclose(weber_margin(score, 15.96), 0.04)


def test_preprocess_shapes() -> None:
    values = np.sin(np.linspace(0, 5, 101))
    processed = preprocess_signal(values, smooth_window=3, noise_window=11)
    assert all(len(processed[key]) == len(values) for key in ("raw", "smooth", "sigma", "lower", "upper"))
    assert np.all(processed["upper"] >= processed["lower"])


def test_evidence_agreement_conflict() -> None:
    result = evidence_agreement(score=25, boundary=15.96, stability=0.2, robustness=0.2, overlap_flag=False)
    assert result["agreement"] == "Conflict detected"


def test_parameter_robustness_is_probability() -> None:
    x = np.arange(301)
    values = 0.05 + 0.01 * np.exp(-0.5 * ((x - 150) / 8) ** 2)
    config = DetectorConfig(perturbation_runs=5)
    robustness, matrix, smoothing, k_values = parameter_robustness(values, 150, config)
    assert 0 <= robustness <= 1
    assert matrix.shape == (len(smoothing), len(k_values))
