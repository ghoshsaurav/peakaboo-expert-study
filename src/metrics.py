from __future__ import annotations

import json
from typing import Any

import numpy as np
import pandas as pd


DECISION_ACCEPT = 1
DECISION_REJECT = 2
DECISION_DEFER = 3


def _safe_json_list(value: Any) -> list[str]:
    if isinstance(value, list):
        return [str(item) for item in value]
    if value is None or (isinstance(value, float) and np.isnan(value)):
        return []
    try:
        parsed = json.loads(str(value))
    except (json.JSONDecodeError, TypeError):
        return [str(value)]
    return [str(item) for item in parsed] if isinstance(parsed, list) else [str(parsed)]


def _evidence_code(label: str) -> str:
    return (
        "used_"
        + label.lower()
        .replace("–", "-")
        .replace("/", "_")
        .replace(" ", "_")
        .replace("-", "_")
        .replace(".", "")
    )


def analysis_ready_trials(assignments: pd.DataFrame, responses: pd.DataFrame) -> pd.DataFrame:
    if assignments.empty:
        return pd.DataFrame()
    assignment = assignments.copy()
    if "assignment_json" in assignment.columns:
        expanded = pd.DataFrame([json.loads(value) for value in assignment["assignment_json"]])
        expanded.insert(0, "session_id", assignment["session_id"].astype(str).to_numpy())
        assignment = expanded
    keys = [column for column in ("session_id", "trial_id", "case_id", "condition") if column in assignment.columns]
    merged = assignment.merge(responses, on=keys, how="left", suffixes=("", "_response"))

    if "selected_evidence_json" in merged.columns:
        evidence_lists = merged["selected_evidence_json"].apply(_safe_json_list)
        evidence_values = sorted({item for values in evidence_lists for item in values})
        for label in evidence_values:
            merged[_evidence_code(label)] = evidence_lists.apply(lambda values, target=label: int(target in values))

    if "hidden_reference_status" in merged.columns and "decision_code" in merged.columns:
        status = merged["hidden_reference_status"].astype(str).str.lower()
        supported = status.eq("supported")
        unsupported = status.isin(["unsupported", "oversegmented", "duplicate"])
        merged["reference_supported"] = supported.astype(int)
        merged["reference_unsupported"] = unsupported.astype(int)
        merged["reference_expected_decision"] = np.select(
            [supported, unsupported],
            [DECISION_ACCEPT, DECISION_REJECT],
            default=np.nan,
        )
        merged["supported_accept"] = ((merged["decision_code"] == DECISION_ACCEPT) & supported).astype(int)
        merged["unsupported_reject"] = ((merged["decision_code"] == DECISION_REJECT) & unsupported).astype(int)
        merged["unsupported_accept"] = ((merged["decision_code"] == DECISION_ACCEPT) & unsupported).astype(int)
        merged["supported_reject"] = ((merged["decision_code"] == DECISION_REJECT) & supported).astype(int)
        conflict = merged.get("hidden_disagreement_type", pd.Series("none", index=merged.index)).astype(str).ne("none")
        merged["case_has_evidence_conflict"] = conflict.astype(int)
        merged["appropriate_defer"] = ((merged["decision_code"] == DECISION_DEFER) & conflict).astype(int)
        merged["reference_alignment"] = np.where(
            merged["reference_expected_decision"].notna(),
            (merged["decision_code"] == merged["reference_expected_decision"]).astype(int),
            np.nan,
        )
        # Backward-compatible name used by prior scripts.
        merged["reference_agreement"] = merged["reference_alignment"]
        merged["confidence_probability"] = pd.to_numeric(merged.get("confidence"), errors="coerce") / 100.0
        merged["calibration_error"] = np.where(
            merged["reference_alignment"].notna(),
            (merged["confidence_probability"] - merged["reference_alignment"]).abs(),
            np.nan,
        )

    recommendation_column = "recommendation" if "recommendation" in merged.columns else "algorithmic_recommendation"
    if recommendation_column in merged.columns and "decision_code" in merged.columns:
        recommendation_to_code = {"Accept": DECISION_ACCEPT, "Reject": DECISION_REJECT, "Defer": DECISION_DEFER}
        rec_code = merged[recommendation_column].map(recommendation_to_code)
        merged["recommendation_code"] = rec_code
        merged["recommendation_followed_derived"] = np.where(
            rec_code.notna(),
            (merged["decision_code"] == rec_code).astype(int),
            np.nan,
        )
        if "reference_expected_decision" in merged.columns:
            rec_aligned = rec_code.eq(merged["reference_expected_decision"]) & rec_code.notna()
            merged["recommendation_reference_aligned"] = np.where(rec_code.notna(), rec_aligned.astype(int), np.nan)
            followed = merged["recommendation_followed_derived"].eq(1)
            category = np.select(
                [
                    rec_code.notna() & rec_aligned & followed,
                    rec_code.notna() & (~rec_aligned) & followed,
                    rec_code.notna() & rec_aligned & (~followed),
                    rec_code.notna() & (~rec_aligned) & (~followed),
                ],
                [
                    "appropriate_reliance",
                    "over_reliance",
                    "under_reliance",
                    "appropriate_skepticism",
                ],
                default=None,
            )
            merged["reliance_category"] = category

    return merged


def descriptive_summary(trials: pd.DataFrame) -> dict[str, Any]:
    if trials.empty:
        return {
            "participants": 0,
            "completed_trials": 0,
            "accept_rate": np.nan,
            "reject_rate": np.nan,
            "defer_rate": np.nan,
            "mean_confidence": np.nan,
        }
    completed = trials[trials["decision_code"].notna()].copy()
    count = max(len(completed), 1)
    return {
        "participants": int(completed["session_id"].nunique()) if "session_id" in completed else 0,
        "completed_trials": int(len(completed)),
        "accept_rate": float((completed["decision_code"] == DECISION_ACCEPT).sum() / count),
        "reject_rate": float((completed["decision_code"] == DECISION_REJECT).sum() / count),
        "defer_rate": float((completed["decision_code"] == DECISION_DEFER).sum() / count),
        "mean_confidence": float(completed["confidence"].mean()) if "confidence" in completed else np.nan,
        "mean_response_time_seconds": float(completed["response_time_seconds"].mean())
        if "response_time_seconds" in completed
        else np.nan,
        "reference_alignment_rate": float(completed["reference_alignment"].mean())
        if "reference_alignment" in completed
        else np.nan,
        "mean_calibration_error": float(completed["calibration_error"].mean())
        if "calibration_error" in completed
        else np.nan,
        "unsupported_acceptance_rate": float(
            completed.loc[completed.get("reference_unsupported", 0) == 1, "unsupported_accept"].mean()
        )
        if "unsupported_accept" in completed and (completed.get("reference_unsupported", 0) == 1).any()
        else np.nan,
        "supported_rejection_rate": float(
            completed.loc[completed.get("reference_supported", 0) == 1, "supported_reject"].mean()
        )
        if "supported_reject" in completed and (completed.get("reference_supported", 0) == 1).any()
        else np.nan,
    }


def condition_summary(trials: pd.DataFrame) -> pd.DataFrame:
    if trials.empty or "condition" not in trials:
        return pd.DataFrame()
    records: list[dict[str, Any]] = []
    for condition, group in trials.groupby("condition", dropna=False):
        completed = group[group["decision_code"].notna()]
        if completed.empty:
            continue
        records.append(
            {
                "condition": condition,
                "n_trials": len(completed),
                "n_participants": completed["session_id"].nunique(),
                "accept_rate": (completed["decision_code"] == DECISION_ACCEPT).mean(),
                "reject_rate": (completed["decision_code"] == DECISION_REJECT).mean(),
                "defer_rate": (completed["decision_code"] == DECISION_DEFER).mean(),
                "mean_confidence": completed["confidence"].mean(),
                "mean_response_time_seconds": completed["response_time_seconds"].mean(),
                "reference_alignment_rate": completed["reference_alignment"].mean()
                if "reference_alignment" in completed
                else np.nan,
                "mean_calibration_error": completed["calibration_error"].mean()
                if "calibration_error" in completed
                else np.nan,
                "unsupported_acceptance_rate": completed.loc[
                    completed.get("reference_unsupported", 0) == 1, "unsupported_accept"
                ].mean()
                if "unsupported_accept" in completed and (completed.get("reference_unsupported", 0) == 1).any()
                else np.nan,
                "supported_rejection_rate": completed.loc[
                    completed.get("reference_supported", 0) == 1, "supported_reject"
                ].mean()
                if "supported_reject" in completed and (completed.get("reference_supported", 0) == 1).any()
                else np.nan,
            }
        )
    return pd.DataFrame(records)


def evidence_frequency(trials: pd.DataFrame) -> pd.DataFrame:
    evidence_columns = [column for column in trials.columns if column.startswith("used_")]
    if not evidence_columns:
        return pd.DataFrame(columns=["evidence", "count", "rate"])
    records = []
    completed_n = max(int(trials["decision_code"].notna().sum()), 1) if "decision_code" in trials else max(len(trials), 1)
    for column in evidence_columns:
        count = int(pd.to_numeric(trials[column], errors="coerce").fillna(0).sum())
        records.append({"evidence": column.removeprefix("used_"), "count": count, "rate": count / completed_n})
    return pd.DataFrame(records).sort_values("count", ascending=False)


def reliance_summary(trials: pd.DataFrame) -> pd.DataFrame:
    if "reliance_category" not in trials.columns:
        return pd.DataFrame(columns=["reliance_category", "count", "rate"])
    subset = trials.dropna(subset=["reliance_category"]).copy()
    if subset.empty:
        return pd.DataFrame(columns=["reliance_category", "count", "rate"])
    counts = subset["reliance_category"].value_counts().rename_axis("reliance_category").reset_index(name="count")
    counts["rate"] = counts["count"] / counts["count"].sum()
    return counts


def conflict_summary(trials: pd.DataFrame) -> pd.DataFrame:
    if trials.empty or "case_has_evidence_conflict" not in trials.columns:
        return pd.DataFrame()
    completed = trials.dropna(subset=["decision_code"]).copy()
    return completed.groupby(["condition", "case_has_evidence_conflict"], as_index=False).agg(
        n_trials=("trial_id", "count"),
        defer_rate=("decision_code", lambda x: (x == DECISION_DEFER).mean()),
        reference_alignment_rate=("reference_alignment", "mean"),
        mean_confidence=("confidence", "mean"),
        mean_response_time_seconds=("response_time_seconds", "mean"),
        mean_clarity=("clarity", "mean"),
    )


def same_case_decision_changes(trials: pd.DataFrame) -> pd.DataFrame:
    """Create one row per participant and shared case for direct condition comparison."""
    if trials.empty or not {"session_id", "case_id", "condition", "decision_code"}.issubset(trials.columns):
        return pd.DataFrame()
    completed = trials.dropna(subset=["decision_code"]).copy()
    if completed.empty:
        return pd.DataFrame()

    index_columns = ["session_id", "case_id"]
    if "case_slot" in completed.columns:
        index_columns.append("case_slot")
    decision = completed.pivot_table(
        index=index_columns,
        columns="condition",
        values="decision_code",
        aggfunc="first",
    )
    confidence = completed.pivot_table(
        index=index_columns,
        columns="condition",
        values="confidence",
        aggfunc="first",
    )
    decision.columns = [f"decision_{column}" for column in decision.columns]
    confidence.columns = [f"confidence_{column}" for column in confidence.columns]
    result = decision.join(confidence, how="outer").reset_index()

    baseline = result.get("decision_baseline")
    evidence = result.get("decision_peakaboo")
    recommendation = result.get("decision_peakaboo_recommendation")
    if baseline is not None and evidence is not None:
        result["changed_after_evidence"] = (baseline != evidence).astype(int)
    if evidence is not None and recommendation is not None:
        result["changed_after_ai_peak_mark"] = (evidence != recommendation).astype(int)
    if baseline is not None and recommendation is not None:
        result["changed_from_baseline_to_ai"] = (baseline != recommendation).astype(int)

    reference = completed.groupby(index_columns, as_index=False).agg(
        hidden_reference_status=("hidden_reference_status", "first"),
        hidden_case_category=("hidden_case_category", "first"),
        hidden_disagreement_type=("hidden_disagreement_type", "first"),
    )
    return result.merge(reference, on=index_columns, how="left")
