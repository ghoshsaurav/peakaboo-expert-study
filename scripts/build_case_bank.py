#!/usr/bin/env python3
"""Build the 48-case expert-study bank from synthetic and approved research signals."""

from __future__ import annotations

import argparse
import hashlib
import json
import sys
from dataclasses import asdict, replace
from pathlib import Path
from typing import Any

import h5py
import numpy as np
import pandas as pd
from scipy.signal import find_peaks, peak_widths

ROOT = Path(__file__).resolve().parents[1]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

from src.evidence import (  # noqa: E402
    DetectorConfig,
    algorithmic_recommendation,
    baseline_drift_score,
    detect_candidates,
    detectability,
    evidence_agreement,
    nearest_peak_structure,
    parameter_robustness,
    perturbation_stability,
    preprocess_signal,
    prominence_at_candidate,
    provenance_json,
    segment_boundary_distance,
    weber_margin,
)


def stable_seed(text: str) -> int:
    """Create a deterministic random seed from case-identifying text."""
    return int(hashlib.sha256(text.encode("utf-8")).hexdigest()[:8], 16)


def bool_value(value: Any) -> bool:
    """Normalize string or scalar values into booleans when reading metadata."""
    return bool(value) if not isinstance(value, str) else value.lower() in {"1", "true", "yes"}


def compute_case(
    case_id: str,
    source_type: str,
    source_name: str,
    channel_id: str,
    time_values: np.ndarray,
    raw_values: np.ndarray,
    candidate_index: int,
    reference_status: str,
    initial_category: str,
    config: DetectorConfig,
    reference_interval: tuple[float, float] | None = None,
    extra_provenance: dict[str, Any] | None = None,
) -> tuple[dict[str, Any], dict[str, np.ndarray]]:
    """Compute all study evidence and stored signal arrays for one candidate case."""
    processed = preprocess_signal(raw_values, config.smooth_window, config.noise_window)
    local_candidate = int(np.clip(candidate_index, 2, len(raw_values) - 3))
    local_search = np.arange(max(1, local_candidate - 3), min(len(raw_values) - 1, local_candidate + 4))
    local_candidate = int(local_search[np.argmax(processed["smooth"][local_search])])
    prominence, width = prominence_at_candidate(processed["smooth"], local_candidate)
    local_noise = float(processed["sigma"][local_candidate])
    score = detectability(prominence, local_noise)
    margin = weber_margin(score, config.weber_boundary)

    structure = nearest_peak_structure(processed["smooth"], local_candidate, width, candidate_prominence=prominence, distance=1)
    drift = baseline_drift_score(processed["smooth"], local_candidate)
    boundary_distance = segment_boundary_distance(local_candidate, config.segment_points, config.overlap_points)
    stability, stability_hits, stability_offsets = perturbation_stability(
        raw_values,
        local_candidate,
        processed["sigma"],
        config,
        seed=stable_seed(f"stability|{case_id}"),
    )
    robustness, matrix, smoothing_values, k_values = parameter_robustness(
        raw_values,
        local_candidate,
        config,
    )
    agreement = evidence_agreement(
        score,
        config.weber_boundary,
        stability,
        robustness,
        structure["overlap_flag"],
    )
    recommendation = algorithmic_recommendation(
        score,
        config.weber_boundary,
        stability,
        robustness,
        structure["overlap_flag"],
        structure["duplicate_risk"],
    )

    disagreement = "none"
    if (score >= config.weber_boundary) != (stability >= 0.70):
        disagreement = "detectability_vs_stability"
    elif (score >= config.weber_boundary) != (robustness >= 0.60):
        disagreement = "detectability_vs_parameter_robustness"
    if reference_status == "unsupported" and recommendation == "Accept":
        disagreement = "favorable_algorithm_vs_unsupported_reference"
    elif reference_status == "supported" and recommendation == "Reject":
        disagreement = "unfavorable_algorithm_vs_supported_reference"

    category = initial_category
    if source_type == "real":
        if reference_status == "unsupported" and stability >= 0.80:
            category = "stable_unsupported"
        elif reference_status == "supported" and stability < 0.50:
            category = "unstable_supported"
        elif abs(margin) <= 3.0:
            category = "near_boundary"
        elif structure["overlap_flag"]:
            category = "overlap_or_duplicate"
        elif robustness < 0.50:
            category = "parameter_sensitive"
        elif drift >= 0.20:
            category = "baseline_drift"
        elif score >= config.weber_boundary and stability >= 0.70:
            category = "high_detectability_high_stability"
        else:
            category = "mixed_evidence"

    signal_key = case_id
    interval_start = reference_interval[0] if reference_interval else np.nan
    interval_end = reference_interval[1] if reference_interval else np.nan
    record = {
        "case_id": case_id,
        "pair_id": "",  # assigned after all cases are created
        "source_type": source_type,
        "source_name": source_name,
        "channel_id": channel_id,
        "condition_eligible": "baseline|peakaboo|peakaboo_recommendation",
        "candidate_time": float(time_values[local_candidate]),
        "window_start": float(time_values[0]),
        "window_end": float(time_values[-1]),
        "signal_key": signal_key,
        "hidden_reference_status": reference_status,
        "hidden_case_category": category,
        "hidden_disagreement_type": disagreement,
        "hidden_expected_recommendation": recommendation,
        "reference_interval_start": interval_start,
        "reference_interval_end": interval_end,
        "peak_height": float(processed["smooth"][local_candidate]),
        "prominence": float(prominence),
        "local_noise": local_noise,
        "detectability": float(score),
        "weber_boundary": float(config.weber_boundary),
        "weber_margin": float(margin),
        "stability": float(stability),
        "stability_runs": int(len(stability_hits)),
        "stability_hits": int(stability_hits.sum()),
        "parameter_robustness": float(robustness),
        "parameter_runs": int(matrix.size),
        "parameter_hits": int(matrix.sum()),
        "width_samples": float(width),
        "nearest_distance_samples": float(structure["nearest_distance_samples"]),
        "separation_width_ratio": float(structure["separation_width_ratio"]),
        "overlap_flag": bool(structure["overlap_flag"]),
        "duplicate_risk": structure["duplicate_risk"],
        "baseline_drift_score": float(drift),
        "segment_boundary_distance": int(boundary_distance),
        "evidence_agreement": agreement["agreement"],
        "algorithmic_recommendation": recommendation,
        "provenance_json": provenance_json(config, extra=extra_provenance),
        "explanation_trial_eligible": disagreement != "none" or category not in {"clear_supported", "clear_unsupported"},
        "pilot_ready": True,
    }
    arrays = {
        f"{signal_key}__time": np.asarray(time_values, dtype=float),
        f"{signal_key}__raw": np.asarray(raw_values, dtype=float),
        f"{signal_key}__smooth": processed["smooth"].astype(float),
        f"{signal_key}__sigma": processed["sigma"].astype(float),
        f"{signal_key}__lower": processed["lower"].astype(float),
        f"{signal_key}__upper": processed["upper"].astype(float),
        f"{signal_key}__candidate_index": np.asarray([local_candidate], dtype=int),
        f"{signal_key}__nearby_peak_indices": np.asarray(structure["nearby_peak_indices"], dtype=int),
        f"{signal_key}__stability_hits": stability_hits.astype(int),
        f"{signal_key}__stability_offsets": stability_offsets.astype(float),
        f"{signal_key}__parameter_matrix": matrix.astype(int),
        f"{signal_key}__parameter_smoothing": smoothing_values.astype(int),
        f"{signal_key}__parameter_k": k_values.astype(float),
    }
    return record, arrays


def gaussian(x: np.ndarray, center: float, width: float, amplitude: float) -> np.ndarray:
    """Return a Gaussian component used to create a controlled synthetic case."""
    return amplitude * np.exp(-0.5 * ((x - center) / width) ** 2)


def synthetic_case_signal(category: str, replicate: int) -> tuple[np.ndarray, np.ndarray, int, str, DetectorConfig, dict[str, Any]]:
    """Generate one controlled synthetic signal for a named ambiguity/failure category."""
    rng = np.random.default_rng(stable_seed(f"synthetic|{category}|{replicate}"))
    n = 401
    time_values = np.linspace(8.0, 12.0, n)
    x = np.arange(n, dtype=float)
    center = 200 + (replicate * 3 - 2)
    baseline = 0.05 + 0.000002 * (x - center)
    noise_sd = 0.00055
    signal = baseline.copy()
    reference_status = "supported"
    config = DetectorConfig(perturbation_runs=30, match_tolerance=6)
    extra: dict[str, Any] = {"synthetic_category": category, "synthetic_replicate": replicate}

    if category == "clear_supported":
        signal += gaussian(x, center, 12, 0.018)
        noise_sd = 0.00035
    elif category == "clear_unsupported":
        signal += gaussian(x, center, 3.0, 0.009)
        noise_sd = 0.00045
        reference_status = "unsupported"
        extra["synthetic_rationale"] = "strong instrument-like spike without a reference interval"
    elif category == "near_boundary_supported":
        signal += gaussian(x, center, 8, 0.024)
        noise_sd = 0.0012
    elif category == "near_boundary_unsupported":
        signal += gaussian(x, center, 7, 0.019)
        noise_sd = 0.00125
        reference_status = "unsupported"
    elif category == "stable_unsupported":
        signal += gaussian(x, center, 10, 0.015)
        noise_sd = 0.00035
        reference_status = "unsupported"
        config = replace(config, perturbation_scale=0.35)
    elif category == "unstable_supported":
        signal += gaussian(x, center, 3.2, 0.0012)
        noise_sd = 0.0015
        config = replace(config, perturbation_scale=1.0, match_tolerance=4)
    elif category == "high_detectability_low_stability":
        signal += gaussian(x, center - 4, 3.0, 0.0120)
        signal += gaussian(x, center + 4, 3.0, 0.0118)
        noise_sd = 0.00030
        config = replace(config, match_tolerance=1, perturbation_scale=1.10)
    elif category == "low_detectability_high_stability":
        signal += gaussian(x, center, 18, 0.0040)
        noise_sd = 0.0010
        config = replace(config, perturbation_scale=0.03, match_tolerance=14)
    elif category == "overlapping_supported":
        signal += gaussian(x, center - 12, 9, 0.012)
        signal += gaussian(x, center + 12, 9, 0.010)
        center = center - 12
        noise_sd = 0.00045
    elif category == "duplicate_oversegmentation":
        signal += gaussian(x, center, 13, 0.012)
        signal += gaussian(x, center - 4, 2.2, 0.003)
        signal += gaussian(x, center + 4, 2.2, 0.0032)
        noise_sd = 0.0004
        reference_status = "oversegmented"
    elif category == "baseline_drift":
        baseline = 0.045 + 0.00007 * x + 0.00000025 * (x - center) ** 2
        signal = baseline + gaussian(x, center, 9, 0.007)
        noise_sd = 0.00065
    elif category == "parameter_sensitive":
        signal += gaussian(x, center - 9, 12, 0.012)
        signal += gaussian(x, center + 5, 3.5, 0.0032)
        center = center + 5
        noise_sd = 0.00055
    else:
        signal += gaussian(x, center, 10, 0.008)

    # Changing local noise makes the local variation band informative without making it a confidence interval.
    local_scale = 1.0 + 1.2 * np.exp(-0.5 * ((x - center) / 35.0) ** 2)
    noise = rng.normal(0.0, noise_sd * local_scale, n)
    raw = signal + noise
    return time_values, raw, int(center), reference_status, config, extra


def build_synthetic_cases() -> tuple[list[dict[str, Any]], dict[str, np.ndarray]]:
    """Build 24 synthetic study cases spanning the planned evidence-conflict categories."""
    categories = [
        "clear_supported",
        "clear_unsupported",
        "near_boundary_supported",
        "near_boundary_unsupported",
        "stable_unsupported",
        "unstable_supported",
        "high_detectability_low_stability",
        "low_detectability_high_stability",
        "overlapping_supported",
        "duplicate_oversegmentation",
        "baseline_drift",
        "parameter_sensitive",
    ]
    records: list[dict[str, Any]] = []
    arrays: dict[str, np.ndarray] = {}
    counter = 1
    for category in categories:
        for replicate in (1, 2):
            case_id = f"SYN-{counter:03d}"
            time_values, raw, candidate_index, reference_status, config, extra = synthetic_case_signal(category, replicate)
            interval = (
                float(time_values[max(0, candidate_index - 15)]),
                float(time_values[min(len(time_values) - 1, candidate_index + 15)]),
            ) if reference_status != "unsupported" else None
            record, case_arrays = compute_case(
                case_id=case_id,
                source_type="synthetic",
                source_name="generated_demo",
                channel_id=f"synthetic_{counter}",
                time_values=time_values,
                raw_values=raw,
                candidate_index=candidate_index,
                reference_status=reference_status,
                initial_category=category,
                config=config,
                reference_interval=interval,
                extra_provenance=extra,
            )
            records.append(record)
            arrays.update(case_arrays)
            counter += 1
    return records, arrays


def valid_labels(path: Path) -> pd.DataFrame:
    """Load the source reference workbook and keep rows with valid time intervals."""
    labels = pd.read_excel(path)
    required = {"ChannelId", "StartTime", "EndTime", "RetentionTime"}
    missing = required - set(labels.columns)
    if missing:
        raise ValueError(f"Reference label file is missing columns: {sorted(missing)}")
    labels = labels[
        labels["StartTime"].notna()
        & labels["EndTime"].notna()
        & labels["RetentionTime"].notna()
        & (labels["StartTime"] >= 0)
        & (labels["EndTime"] > labels["StartTime"])
    ].copy()
    labels["ChannelId"] = labels["ChannelId"].astype(int)
    return labels


def preliminary_real_pool(h5_path: Path, label_path: Path, max_channels: int = 120) -> list[dict[str, Any]]:
    """Scan approved research channels and create a preliminary pool of candidate metadata."""
    labels = valid_labels(label_path)
    labels_by_channel = {channel: frame.copy() for channel, frame in labels.groupby("ChannelId")}
    config = DetectorConfig(perturbation_runs=20)
    pool: list[dict[str, Any]] = []
    with h5py.File(h5_path, "r") as archive:
        channels = [key for key in archive.keys() if int(key) in labels_by_channel][:max_channels]
        for channel in channels:
            time_values = np.asarray(archive[channel]["time"][:], dtype=float)
            raw = np.asarray(archive[channel]["values"][:], dtype=float)
            peaks, props, processed = detect_candidates(
                raw,
                smooth_window=config.smooth_window,
                noise_window=config.noise_window,
                distance=config.distance,
                prominence_floor=config.prominence_floor,
                local_k=None,
            )
            if len(peaks) == 0:
                continue
            channel_labels = labels_by_channel[int(channel)].reset_index(drop=True)
            intervals = channel_labels[["StartTime", "EndTime"]].to_numpy(dtype=float)
            # Map interval -> candidate with maximum prominence.
            candidate_intervals: dict[int, list[int]] = {}
            for candidate_position, peak_index in enumerate(peaks):
                time_value = time_values[peak_index]
                matching = np.where((intervals[:, 0] <= time_value) & (time_value <= intervals[:, 1]))[0]
                for interval_index in matching:
                    candidate_intervals.setdefault(int(interval_index), []).append(candidate_position)
            strongest: dict[int, int] = {}
            for interval_index, candidates in candidate_intervals.items():
                strongest[interval_index] = max(candidates, key=lambda position: float(props["prominences"][position]))

            widths = props["widths"]
            for position, peak_index in enumerate(peaks):
                time_value = time_values[peak_index]
                matching = np.where((intervals[:, 0] <= time_value) & (time_value <= intervals[:, 1]))[0]
                status = "unsupported"
                interval = None
                if len(matching):
                    interval_index = int(matching[0])
                    status = "supported" if strongest.get(interval_index) == position else "oversegmented"
                    interval = tuple(intervals[interval_index])
                local_noise = float(processed["sigma"][peak_index])
                score = detectability(float(props["prominences"][position]), local_noise)
                structure = nearest_peak_structure(processed["smooth"], int(peak_index), float(widths[position]), candidate_prominence=float(props["prominences"][position]), distance=1)
                drift = baseline_drift_score(processed["smooth"], int(peak_index))
                pool.append(
                    {
                        "channel": channel,
                        "peak_index": int(peak_index),
                        "candidate_time": float(time_value),
                        "prominence": float(props["prominences"][position]),
                        "local_noise": local_noise,
                        "detectability": score,
                        "margin": score - config.weber_boundary,
                        "width": float(widths[position]),
                        "reference_status": status,
                        "reference_interval": interval,
                        "overlap_flag": bool(structure["overlap_flag"]),
                        "drift": drift,
                    }
                )
    return pool


def select_real_candidates(pool: list[dict[str, Any]], count: int = 24) -> list[dict[str, Any]]:
    """Select a diverse set of research candidates emphasizing difficult evidence patterns."""
    frame = pd.DataFrame(pool)
    if frame.empty:
        return []
    frame["selection_key"] = frame["channel"].astype(str) + ":" + frame["peak_index"].astype(str)
    selected: list[pd.Series] = []
    used: set[str] = set()

    def add(subset: pd.DataFrame, n: int, sort_column: str | None = None, ascending: bool = True) -> None:
        """Add up to ``n`` previously unused candidates from a prioritized subset."""
        nonlocal selected
        subset = subset.loc[~subset["selection_key"].isin(used)].copy()
        if sort_column:
            subset = subset.sort_values(sort_column, ascending=ascending)
        else:
            subset = subset.sample(frac=1.0, random_state=20260804)
        for _, row in subset.head(n).iterrows():
            selected.append(row)
            used.add(str(row["selection_key"]))

    add(frame.loc[frame["margin"].abs() <= 4.0], 4, "margin", True)
    add(frame.loc[(frame["reference_status"] == "unsupported") & (frame["detectability"] >= 20)], 4, "detectability", False)
    add(frame.loc[(frame["reference_status"] == "supported") & (frame["detectability"] < 15.96)], 4, "detectability", True)
    add(frame.loc[frame["overlap_flag"]], 4, "detectability", False)
    add(frame, 4, "drift", False)
    add(frame.loc[frame["reference_status"] == "supported"], 2, "detectability", False)
    add(frame.loc[frame["reference_status"] == "unsupported"], 2, "detectability", True)
    if len(selected) < count:
        add(frame, count - len(selected), None)
    return [row.to_dict() for row in selected[:count]]


def build_real_cases(h5_path: Path, label_path: Path, count: int = 24) -> tuple[list[dict[str, Any]], dict[str, np.ndarray]]:
    """Build study records and self-contained signal windows for selected research candidates."""
    pool = preliminary_real_pool(h5_path, label_path)
    selected = select_real_candidates(pool, count=count)
    if len(selected) < count:
        raise RuntimeError(f"Only {len(selected)} real candidates could be selected")

    records: list[dict[str, Any]] = []
    arrays: dict[str, np.ndarray] = {}
    config = DetectorConfig(perturbation_runs=30)
    with h5py.File(h5_path, "r") as archive:
        for counter, candidate in enumerate(selected, start=1):
            channel = str(candidate["channel"])
            full_time = np.asarray(archive[channel]["time"][:], dtype=float)
            full_raw = np.asarray(archive[channel]["values"][:], dtype=float)
            center = int(candidate["peak_index"])
            radius = 180
            left = max(0, center - radius)
            right = min(len(full_raw), center + radius + 1)
            time_values = full_time[left:right]
            raw = full_raw[left:right]
            local_index = center - left
            case_id = f"REAL-{counter:03d}"
            record, case_arrays = compute_case(
                case_id=case_id,
                source_type="real",
                source_name=Path(h5_path).name,
                channel_id=channel,
                time_values=time_values,
                raw_values=raw,
                candidate_index=local_index,
                reference_status=str(candidate["reference_status"]),
                initial_category="real_candidate",
                config=config,
                reference_interval=candidate.get("reference_interval"),
                extra_provenance={
                    "source_peak_index": center,
                    "source_time_range": [float(full_time[0]), float(full_time[-1])],
                    "source_label_file": Path(label_path).name,
                },
            )
            records.append(record)
            arrays.update(case_arrays)
    return records, arrays


def assign_pairs(records: list[dict[str, Any]]) -> None:
    """Assign approximate two-case matching groups separately within synthetic and research sources."""
    for source_type in ("synthetic", "real"):
        source_records = [record for record in records if record["source_type"] == source_type]
        # Sort by category, then evidence values so paired cases are approximately matched but not identical.
        source_records.sort(
            key=lambda record: (
                record["hidden_case_category"],
                round(float(record["detectability"]), 1),
                round(float(record["stability"]), 1),
            )
        )
        for pair_index in range(0, len(source_records), 2):
            pair_number = pair_index // 2 + 1
            pair_id = f"{source_type[:3].upper()}-PAIR-{pair_number:02d}"
            for record in source_records[pair_index : pair_index + 2]:
                record["pair_id"] = pair_id


def validate_records(records: list[dict[str, Any]]) -> None:
    """Assert the final bank contains 48 unique, paired, pilot-ready cases with balanced sources."""
    frame = pd.DataFrame(records)
    if len(frame) != 48:
        raise AssertionError(f"Expected 48 cases, found {len(frame)}")
    if frame["case_id"].duplicated().any():
        raise AssertionError("Duplicate case IDs")
    counts = frame.groupby("source_type").size().to_dict()
    if counts != {"real": 24, "synthetic": 24}:
        raise AssertionError(f"Expected 24 real and 24 synthetic cases, found {counts}")
    pair_sizes = frame.groupby("pair_id").size()
    if not (pair_sizes == 2).all():
        raise AssertionError(f"Every pair must contain exactly two cases: {pair_sizes.to_dict()}")
    if not frame["pilot_ready"].astype(bool).all():
        raise AssertionError("All demo cases should be pilot-ready")


def main() -> None:
    """Build, validate, and save case metadata, signal arrays, and a summary manifest."""
    parser = argparse.ArgumentParser(description="Build the 48-case Peak-a-boo expert-study case bank.")
    parser.add_argument("--h5", type=Path, required=True, help="Path to chromatograms.h5")
    parser.add_argument("--labels", type=Path, required=True, help="Path to peak_df.xlsx")
    parser.add_argument("--output-dir", type=Path, default=ROOT / "data" / "demo")
    args = parser.parse_args()

    args.output_dir.mkdir(parents=True, exist_ok=True)
    synthetic_records, synthetic_arrays = build_synthetic_cases()
    real_records, real_arrays = build_real_cases(args.h5, args.labels)
    records = synthetic_records + real_records
    assign_pairs(records)
    validate_records(records)

    frame = pd.DataFrame(records).sort_values("case_id").reset_index(drop=True)
    frame.to_csv(args.output_dir / "case_bank.csv", index=False)
    all_arrays = {**synthetic_arrays, **real_arrays}
    np.savez_compressed(args.output_dir / "signals.npz", **all_arrays)

    summary = {
        "cases": len(frame),
        "source_counts": frame["source_type"].value_counts().to_dict(),
        "category_counts": frame["hidden_case_category"].value_counts().to_dict(),
        "disagreement_counts": frame["hidden_disagreement_type"].value_counts().to_dict(),
        "reference_counts": frame["hidden_reference_status"].value_counts().to_dict(),
    }
    (args.output_dir / "case_bank_summary.json").write_text(json.dumps(summary, indent=2), encoding="utf-8")
    print(json.dumps(summary, indent=2))


if __name__ == "__main__":
    main()
