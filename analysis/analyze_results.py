#!/usr/bin/env python3
"""Generate reproducible, RQ-aligned summaries from the expert-study database.

This module is the command-line analysis entry point for the study. It reads the
normalized SQLite/PostgreSQL study tables through :class:`StudyStore`, expands
assignments and trial responses into the analysis-ready table defined in
``src.metrics``, and writes descriptive summaries used by the researcher
dashboard and paper-figure pipeline.

The analysis intentionally treats ``hidden_reference_status`` as a study
comparison label rather than chemical ground truth. Inferential modeling is
therefore exploratory and is skipped for very small pilot datasets.
"""
from __future__ import annotations

import argparse
import json
import sys
from pathlib import Path

import numpy as np
import pandas as pd

# Add the repository root so this script can be executed directly from the
# command line without installing the project as a package.
ROOT = Path(__file__).resolve().parents[1]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

from src.config import load_config, resolve_paths  # noqa: E402
from src.logging_store import StudyStore  # noqa: E402
from src.metrics import (  # noqa: E402
    analysis_ready_trials,
    condition_summary,
    conflict_summary,
    evidence_frequency,
    reliance_summary,
    same_case_decision_changes,
)


def wilson_interval(successes: int, total: int, z: float = 1.96) -> tuple[float, float]:
    """Return a Wilson-score confidence interval for a binomial proportion.

    Wilson intervals are used instead of the simple normal approximation because
    decision rates can be close to 0 or 1 and pilot sample sizes can be small.
    ``z=1.96`` gives the conventional approximate 95% interval.
    """
    if total <= 0:
        return np.nan, np.nan
    p = successes / total
    denominator = 1 + z**2 / total
    center = (p + z**2 / (2 * total)) / denominator
    half = z * np.sqrt((p * (1 - p) / total) + z**2 / (4 * total**2)) / denominator
    return max(0.0, center - half), min(1.0, center + half)


def decision_rates_with_ci(trials: pd.DataFrame) -> pd.DataFrame:
    """Summarize accept/reject/defer rates and Wilson intervals by condition."""
    records: list[dict[str, object]] = []
    completed = trials.dropna(subset=["decision_code", "condition"])
    for condition, group in completed.groupby("condition"):
        total = len(group)
        for label, code in (("accept", 1), ("reject", 2), ("defer", 3)):
            successes = int((group["decision_code"] == code).sum())
            low, high = wilson_interval(successes, total)
            records.append(
                {
                    "condition": condition,
                    "decision": label,
                    "count": successes,
                    "n": total,
                    "rate": successes / total if total else np.nan,
                    "ci95_low": low,
                    "ci95_high": high,
                }
            )
    return pd.DataFrame(records)


def participant_condition_summary(trials: pd.DataFrame) -> pd.DataFrame:
    """Create one row per participant and condition for within-person analysis."""
    completed = trials.dropna(subset=["decision_code"]).copy()
    if completed.empty:
        return pd.DataFrame()
    return completed.groupby(["session_id", "condition"], as_index=False).agg(
        n_trials=("trial_id", "count"),
        accept_rate=("decision_code", lambda values: (values == 1).mean()),
        reject_rate=("decision_code", lambda values: (values == 2).mean()),
        defer_rate=("decision_code", lambda values: (values == 3).mean()),
        mean_confidence=("confidence", "mean"),
        mean_response_time=("response_time_seconds", "mean"),
        reference_alignment_rate=("reference_alignment", "mean"),
        mean_calibration_error=("calibration_error", "mean"),
    )


def confidence_calibration(trials: pd.DataFrame) -> pd.DataFrame:
    """Bin self-reported confidence and compare it with reference alignment.

    Confidence is reported on a 0--100 scale. The output is descriptive: it
    shows whether higher stated confidence corresponds to higher agreement with
    the study comparison label, not whether the participant is chemically
    correct.
    """
    completed = trials.dropna(subset=["confidence", "reference_alignment"]).copy()
    if completed.empty:
        return pd.DataFrame()
    # Start the first bin below zero so a confidence value of exactly 0 is kept.
    bins = [-1, 20, 40, 60, 80, 100]
    labels = ["0–20", "21–40", "41–60", "61–80", "81–100"]
    completed["confidence_bin"] = pd.cut(completed["confidence"], bins=bins, labels=labels)
    return completed.groupby(["condition", "confidence_bin"], observed=True, as_index=False).agg(
        n=("trial_id", "count"),
        mean_confidence=("confidence", "mean"),
        reference_alignment_rate=("reference_alignment", "mean"),
    )


def survey_summary(surveys: pd.DataFrame) -> pd.DataFrame:
    """Count questionnaire responses by section, item code, and displayed label."""
    if surveys.empty:
        return pd.DataFrame()
    return (
        surveys.groupby(["section", "question_code", "response_label"], dropna=False)
        .size()
        .reset_index(name="count")
        .sort_values(["section", "question_code", "count"], ascending=[True, True, False])
    )


def run_exploratory_models(trials: pd.DataFrame, output_dir: Path) -> None:
    """Fit the exploratory repeated-measures GEE when sample size is adequate.

    The binary outcome is reference alignment. Condition, hidden evidence
    conflict, and their interaction are predictors; participant/session is the
    clustering unit. The minimum-size gate prevents a tiny pilot from being
    presented as if it supported stable inferential estimates.
    """
    completed = trials.dropna(subset=["reference_alignment", "condition", "session_id"]).copy()
    if completed["session_id"].nunique() < 10 or len(completed) < 90:
        (output_dir / "model_note.txt").write_text(
            "Inferential model not run: fewer than 10 participants or 90 completed decisions. "
            "Use descriptive and participant-level summaries for the pilot.\n",
            encoding="utf-8",
        )
        return
    try:
        import statsmodels.api as sm
        import statsmodels.formula.api as smf

        # Exchangeable within-participant correlation is a simple exploratory
        # choice because each participant contributes repeated case decisions.
        model = smf.gee(
            "reference_alignment ~ C(condition) * C(case_has_evidence_conflict)",
            groups="session_id",
            data=completed,
            family=sm.families.Binomial(),
            cov_struct=sm.cov_struct.Exchangeable(),
        )
        result = model.fit()
        (output_dir / "gee_reference_alignment.txt").write_text(result.summary().as_text(), encoding="utf-8")
    except Exception as exc:  # pragma: no cover - diagnostic fallback for optional statsmodels failures
        (output_dir / "model_note.txt").write_text(f"Exploratory GEE failed: {exc}\n", encoding="utf-8")


def main() -> None:
    """Read the study database and write all reproducible analysis outputs."""
    parser = argparse.ArgumentParser(description="Generate RQ-aligned study summaries.")
    parser.add_argument("--database", type=Path, help="Optional SQLite database override; defaults to study_config.yaml.")
    parser.add_argument("--output-dir", type=Path, default=ROOT / "analysis" / "outputs")
    args = parser.parse_args()

    config = load_config()
    paths = resolve_paths(config)
    store = StudyStore(args.database or paths.database)
    args.output_dir.mkdir(parents=True, exist_ok=True)

    # Load normalized study tables once, then derive one analysis-ready table so
    # every downstream export uses the same coding logic from src.metrics.
    sessions = store.table("sessions")
    assignments = store.table("assignments")
    responses = store.table("trial_responses")
    surveys = store.table("survey_responses")
    trials = analysis_ready_trials(assignments, responses)

    # Core descriptive exports used by the researcher dashboard and paper plots.
    trials.to_csv(args.output_dir / "analysis_ready_trials.csv", index=False)
    sessions.to_csv(args.output_dir / "sessions.csv", index=False)
    surveys.to_csv(args.output_dir / "survey_responses.csv", index=False)
    survey_summary(surveys).to_csv(args.output_dir / "survey_response_distribution.csv", index=False)
    condition_summary(trials).to_csv(args.output_dir / "condition_summary.csv", index=False)
    decision_rates_with_ci(trials).to_csv(args.output_dir / "decision_rates_with_ci.csv", index=False)
    participant_condition_summary(trials).to_csv(args.output_dir / "participant_condition_summary.csv", index=False)
    evidence_frequency(trials).to_csv(args.output_dir / "evidence_frequency.csv", index=False)
    confidence_calibration(trials).to_csv(args.output_dir / "confidence_calibration.csv", index=False)
    conflict_summary(trials).to_csv(args.output_dir / "evidence_conflict_summary.csv", index=False)
    reliance_summary(trials).to_csv(args.output_dir / "reliance_summary.csv", index=False)
    same_case_decision_changes(trials).to_csv(args.output_dir / "same_case_decision_changes.csv", index=False)

    # Convenience subsets make conflict and recommendation trials easy to audit
    # without changing the canonical analysis-ready table.
    if not trials.empty:
        if "case_has_evidence_conflict" in trials.columns:
            trials.loc[trials["case_has_evidence_conflict"] == 1].to_csv(
                args.output_dir / "evidence_conflict_trials.csv", index=False
            )
        if "condition" in trials.columns:
            trials.loc[trials["condition"].astype(str).eq("peakaboo_recommendation")].to_csv(
                args.output_dir / "recommendation_trials.csv", index=False
            )

    run_exploratory_models(trials, args.output_dir)

    # The manifest records the design assumptions that must accompany any
    # downstream interpretation of the generated files.
    manifest = {
        "database": str(args.database or paths.database),
        "participants": int(trials["session_id"].nunique()) if not trials.empty else 0,
        "completed_decisions": int(trials["decision_code"].notna().sum()) if not trials.empty else 0,
        "decisions_per_participant": 9,
        "decisions_per_condition": 3,
        "unique_cases_per_participant": 3,
        "same_cases_repeated_across_conditions": True,
        "fixed_condition_order": ["baseline", "peakaboo", "peakaboo_recommendation"],
        "interpretation_note": "Reference correspondence is comparison evidence, not chemical correctness.",
    }
    (args.output_dir / "analysis_manifest.json").write_text(json.dumps(manifest, indent=2), encoding="utf-8")
    print(json.dumps(manifest, indent=2))


if __name__ == "__main__":
    main()
