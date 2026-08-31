"""Compute the signal-derived evidence used to build and display study cases."""

from __future__ import annotations

import json
from dataclasses import dataclass
from typing import Any, Iterable

import numpy as np
import pandas as pd
from scipy.signal import find_peaks, peak_prominences, peak_widths


EPSILON = 1e-12


@dataclass(frozen=True)
class DetectorConfig:
    """Store the signal-processing settings used during case/evidence construction."""

    smooth_window: int = 2
    noise_window: int = 51
    distance: int = 22
    prominence_floor: float = 0.00018
    weber_boundary: float = 15.96
    perturbation_runs: int = 30
    perturbation_scale: float = 0.55
    match_tolerance: int = 8
    segment_points: int = 500
    overlap_points: int = 100


def moving_average(values: np.ndarray, window: int) -> np.ndarray:
    """Smooth a signal with a simple moving average."""
    values = np.asarray(values, dtype=float)
    if window <= 1:
        return values.copy()
    kernel = np.ones(int(window), dtype=float) / float(window)
    return np.convolve(values, kernel, mode="same")


def rolling_std(values: np.ndarray, window: int) -> np.ndarray:
    """Estimate centered local standard deviation and fill edge/missing values."""
    values = np.asarray(values, dtype=float)
    min_periods = max(3, int(window) // 4)
    series = pd.Series(values)
    result = (
        series.rolling(int(window), center=True, min_periods=min_periods)
        .std(ddof=0)
        .bfill()
        .ffill()
        .fillna(float(np.nanstd(values) or EPSILON))
    )
    return result.to_numpy(dtype=float)


def preprocess_signal(values: np.ndarray, smooth_window: int, noise_window: int) -> dict[str, np.ndarray]:
    """Return raw, smoothed, residual, local-noise, and uncertainty-band arrays."""
    raw = np.asarray(values, dtype=float)
    smooth = moving_average(raw, smooth_window)
    residual = raw - smooth
    sigma = rolling_std(residual, noise_window)
    lower = smooth - 2.0 * sigma
    upper = smooth + 2.0 * sigma
    return {
        "raw": raw,
        "smooth": smooth,
        "residual": residual,
        "sigma": sigma,
        "lower": lower,
        "upper": upper,
    }


def detect_candidates(
    values: np.ndarray,
    smooth_window: int = 2,
    noise_window: int = 51,
    distance: int = 22,
    prominence_floor: float = 0.00018,
    local_k: float | None = None,
) -> tuple[np.ndarray, dict[str, np.ndarray], dict[str, np.ndarray]]:
    """Detect candidate peaks and optionally require prominence scaled by local noise."""
    processed = preprocess_signal(values, smooth_window, noise_window)
    peaks, props = find_peaks(
        processed["smooth"],
        distance=max(1, int(distance)),
        prominence=max(0.0, float(prominence_floor)),
    )
    if len(peaks) == 0:
        return peaks, {"prominences": np.array([]), "widths": np.array([])}, processed

    prominences = np.asarray(props["prominences"], dtype=float)
    widths = peak_widths(processed["smooth"], peaks, rel_height=0.5)[0]
    if local_k is not None:
        local_threshold = float(local_k) * processed["sigma"][peaks]
        keep = prominences >= np.maximum(float(prominence_floor), local_threshold)
        peaks = peaks[keep]
        prominences = prominences[keep]
        widths = widths[keep]
    return peaks, {"prominences": prominences, "widths": widths}, processed


def prominence_at_candidate(smooth: np.ndarray, candidate_index: int) -> tuple[float, float]:
    """Measure prominence and width near a nominated candidate sample."""
    candidate_index = int(np.clip(candidate_index, 1, len(smooth) - 2))
    # Peak prominence requires a local maximum. Search a small local neighborhood if needed.
    local = np.arange(max(1, candidate_index - 3), min(len(smooth) - 1, candidate_index + 4))
    local_max = int(local[np.argmax(smooth[local])])
    prominence = float(peak_prominences(smooth, np.array([local_max], dtype=int))[0][0])
    width = float(peak_widths(smooth, np.array([local_max], dtype=int), rel_height=0.5)[0][0])
    return max(prominence, 0.0), max(width, EPSILON)


def detectability(prominence: float, local_noise: float) -> float:
    """Return prominence divided by local noise for one candidate."""
    return float(prominence) / (float(local_noise) + EPSILON)


def weber_margin(score: float, boundary: float) -> float:
    """Return the signed distance between detectability and the configured boundary."""
    return float(score) - float(boundary)


def classify_detectability(score: float, boundary: float, near: float = 3.0) -> str:
    """Convert detectability distance into above, near, or below-boundary wording."""
    margin = score - boundary
    if margin > near:
        return "Above boundary"
    if margin < -near:
        return "Below boundary"
    return "Near boundary"


def perturbation_stability(
    values: np.ndarray,
    candidate_index: int,
    sigma: np.ndarray,
    config: DetectorConfig,
    seed: int,
) -> tuple[float, np.ndarray, np.ndarray]:
    """Estimate candidate repeatability across noise-scaled perturbation reruns.

    Each run adds Gaussian noise whose standard deviation is the local noise
    estimate multiplied by ``perturbation_scale``. A run counts as a recovery
    when a detected peak falls within ``match_tolerance`` samples of the original
    candidate.
    """
    rng = np.random.default_rng(seed)
    hits: list[int] = []
    offsets: list[float] = []
    for _ in range(int(config.perturbation_runs)):
        perturbation = rng.normal(0.0, np.maximum(sigma, EPSILON) * float(config.perturbation_scale))
        noisy = np.asarray(values, dtype=float) + perturbation
        peaks, _, _ = detect_candidates(
            noisy,
            smooth_window=config.smooth_window,
            noise_window=config.noise_window,
            distance=config.distance,
            prominence_floor=config.prominence_floor,
            local_k=None,
        )
        if len(peaks) == 0:
            hits.append(0)
            offsets.append(np.nan)
            continue
        distances = np.abs(peaks - int(candidate_index))
        nearest = int(np.argmin(distances))
        if distances[nearest] <= int(config.match_tolerance):
            hits.append(1)
            offsets.append(float(peaks[nearest] - int(candidate_index)))
        else:
            hits.append(0)
            offsets.append(np.nan)
    hit_array = np.asarray(hits, dtype=int)
    return float(hit_array.mean() if len(hit_array) else 0.0), hit_array, np.asarray(offsets, dtype=float)


def parameter_robustness(
    values: np.ndarray,
    candidate_index: int,
    config: DetectorConfig,
    smoothing_values: Iterable[int] = (1, 2, 5, 9),
    k_values: Iterable[float] = (8.0, 12.0, 15.96, 20.0, 24.0),
) -> tuple[float, np.ndarray, np.ndarray, np.ndarray]:
    """Measure how often a candidate survives a grid of smoothing and threshold settings."""
    smooth_grid = np.asarray(list(smoothing_values), dtype=int)
    k_grid = np.asarray(list(k_values), dtype=float)
    matrix = np.zeros((len(smooth_grid), len(k_grid)), dtype=int)
    for row, smooth_window in enumerate(smooth_grid):
        for col, k_value in enumerate(k_grid):
            peaks, _, _ = detect_candidates(
                values,
                smooth_window=int(smooth_window),
                noise_window=config.noise_window,
                distance=config.distance,
                prominence_floor=config.prominence_floor,
                local_k=float(k_value),
            )
            if len(peaks) and np.min(np.abs(peaks - int(candidate_index))) <= int(config.match_tolerance):
                matrix[row, col] = 1
    return float(matrix.mean()), matrix, smooth_grid, k_grid


def nearest_peak_structure(
    smooth: np.ndarray,
    candidate_index: int,
    width_samples: float,
    candidate_prominence: float | None = None,
    distance: int = 1,
) -> dict[str, Any]:
    """Summarize nearby maxima and estimate overlap or duplicate risk around a candidate."""
    # Ignore tiny noise maxima. Structural ambiguity should refer to neighboring
    # candidate-like maxima, not every one-sample fluctuation.
    prominence_threshold = max(
        float(candidate_prominence or 0.0) * 0.20,
        float(np.nanstd(np.diff(smooth))) * 1.5,
        EPSILON,
    )
    minimum_distance = max(2, int(round(max(float(width_samples), 1.0) * 0.20)), int(distance))
    peaks, _ = find_peaks(smooth, distance=minimum_distance, prominence=prominence_threshold)
    others = peaks[np.abs(peaks - int(candidate_index)) > 2]
    if len(others) == 0:
        nearest_distance = float("inf")
        ratio = float("inf")
    else:
        nearest_distance = float(np.min(np.abs(others - int(candidate_index))))
        ratio = nearest_distance / max(float(width_samples), EPSILON)

    if ratio < 1.0:
        duplicate_risk = "High"
    elif ratio < 2.0:
        duplicate_risk = "Moderate"
    else:
        duplicate_risk = "Low"
    return {
        "nearest_distance_samples": nearest_distance,
        "separation_width_ratio": ratio,
        "overlap_flag": bool(ratio < 1.5),
        "duplicate_risk": duplicate_risk,
        "nearby_peak_indices": peaks,
    }


def baseline_drift_score(smooth: np.ndarray, candidate_index: int, radius: int = 60) -> float:
    """Estimate normalized local baseline slope around the candidate."""
    left = max(0, int(candidate_index) - int(radius))
    right = min(len(smooth), int(candidate_index) + int(radius) + 1)
    y = np.asarray(smooth[left:right], dtype=float)
    if len(y) < 4:
        return 0.0
    x = np.linspace(-1.0, 1.0, len(y))
    slope = float(np.polyfit(x, y, 1)[0])
    scale = float(np.ptp(y)) + EPSILON
    return abs(slope) / scale


def segment_boundary_distance(candidate_index: int, segment_points: int, overlap_points: int) -> int:
    """Return distance in samples from a candidate to the nearest segment step boundary."""
    step = max(1, int(segment_points) - int(overlap_points))
    index = int(candidate_index)
    lower = (index // step) * step
    upper = lower + step
    return int(min(abs(index - lower), abs(upper - index)))


def evidence_agreement(
    score: float,
    boundary: float,
    stability: float,
    robustness: float,
    overlap_flag: bool,
) -> dict[str, str]:
    """Summarize whether detectability, stability, robustness, and structure agree."""
    detectability_state = "High" if score >= boundary else "Low"
    stability_state = "High" if stability >= 0.70 else "Low"
    robustness_state = "High" if robustness >= 0.60 else "Low"
    structural_state = "High ambiguity" if overlap_flag else "Low ambiguity"

    favorable = [score >= boundary, stability >= 0.70, robustness >= 0.60, not overlap_flag]
    favorable_count = sum(bool(item) for item in favorable)
    if favorable_count in {0, 4}:
        agreement = "Consistent"
    elif favorable_count in {1, 3}:
        agreement = "Mostly consistent"
    else:
        agreement = "Conflict detected"
    return {
        "agreement": agreement,
        "detectability_state": detectability_state,
        "stability_state": stability_state,
        "robustness_state": robustness_state,
        "structural_state": structural_state,
    }


def algorithmic_recommendation(
    score: float,
    boundary: float,
    stability: float,
    robustness: float,
    overlap_flag: bool,
    duplicate_risk: str,
) -> str:
    """Convert the separate evidence measures into an accept, defer, or reject case label."""
    margin = score - boundary
    if duplicate_risk == "High":
        return "Reject"
    if margin < -3.0:
        # Strong repeatability can conflict with weak local detectability; that is a
        # review case, not an automatic acceptance.
        if stability >= 0.80 and robustness >= 0.70:
            return "Defer"
        return "Reject"
    if abs(margin) <= 3.0 or overlap_flag or (stability < 0.60) or (robustness < 0.50):
        return "Defer"
    return "Accept"


def provenance_json(config: DetectorConfig, extra: dict[str, Any] | None = None) -> str:
    """Serialize the evidence-generation settings so each case can be traced later."""
    payload = {
        "smoothing_method": "moving_average",
        "smooth_window": config.smooth_window,
        "noise_window": config.noise_window,
        "minimum_distance": config.distance,
        "prominence_floor": config.prominence_floor,
        "weber_boundary": config.weber_boundary,
        "perturbation_runs": config.perturbation_runs,
        "perturbation_noise_model": "Normal(0, local_sigma * scale)",
        "perturbation_scale": config.perturbation_scale,
        "matching_tolerance_samples": config.match_tolerance,
        "segment_points": config.segment_points,
        "segment_overlap_points": config.overlap_points,
        "detector_version": "peakaboo-study-1.0",
    }
    if extra:
        payload.update(extra)
    return json.dumps(payload, sort_keys=True)
