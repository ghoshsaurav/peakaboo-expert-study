"""Create deterministic participant assignments for the three-condition expert study."""

from __future__ import annotations

import hashlib
import re
from typing import Iterable

import numpy as np
import pandas as pd


CONDITION_BASELINE = "baseline"
CONDITION_EVIDENCE = "peakaboo"
CONDITION_RECOMMENDATION = "peakaboo_recommendation"
CANONICAL_CONDITION_ORDER = [
    CONDITION_BASELINE,
    CONDITION_EVIDENCE,
    CONDITION_RECOMMENDATION,
]


def stable_int(text: str) -> int:
    """Convert text into a stable integer used for deterministic assignment tie-breaking."""
    digest = hashlib.sha256(text.encode("utf-8")).hexdigest()
    return int(digest[:16], 16)


def participant_counterbalance(participant_id: str, global_seed: int) -> tuple[int, int]:
    """Return a stable cohort and rotation index for selecting case trios.

    The study order is intentionally fixed. Counterbalancing is used only to
    rotate which challenging case trio a participant receives.
    """
    match = re.search(r"(\d+)$", participant_id.strip())
    if match:
        number = max(1, int(match.group(1)))
        return (number - 1) // 6, (number - 1) % 6
    value = stable_int(f"case-trio|{global_seed}|{participant_id}")
    return value // 6, value % 6


def condition_order(participant_id: str, enabled_conditions: list[str], global_seed: int) -> list[str]:
    """Return the fixed study flow: baseline, evidence, then AI recommendation."""
    del participant_id, global_seed
    enabled = list(dict.fromkeys(enabled_conditions))
    ordered = [condition for condition in CANONICAL_CONDITION_ORDER if condition in enabled]
    ordered.extend(condition for condition in enabled if condition not in ordered)
    return ordered


def _challenge_score(bank: pd.DataFrame) -> pd.Series:
    """Score cases for ambiguity without using the score in participant views."""
    category = bank["hidden_case_category"].astype(str)
    disagreement = bank["hidden_disagreement_type"].astype(str)
    margin = pd.to_numeric(bank["weber_margin"], errors="coerce").fillna(0.0)
    stability = pd.to_numeric(bank["stability"], errors="coerce").fillna(0.0)
    robustness = pd.to_numeric(bank["parameter_robustness"], errors="coerce").fillna(0.0)
    overlap = bank.get("overlap_flag", False)
    if not isinstance(overlap, pd.Series):
        overlap = pd.Series(bool(overlap), index=bank.index)
    overlap = overlap.astype(bool)

    score = pd.Series(0.0, index=bank.index)
    score += disagreement.ne("none").astype(float) * 3.0
    score += category.str.contains("near_boundary", case=False).astype(float) * 3.5
    score += category.str.contains("unstable|parameter_sensitive", case=False, regex=True).astype(float) * 2.0
    score += category.str.contains("overlap|duplicate|shoulder", case=False, regex=True).astype(float) * 2.0
    score += category.str.contains("stable_unsupported|low_detectability_high_stability", case=False, regex=True).astype(float) * 2.5
    score += (margin.abs() <= 4).astype(float) * 3.0
    score += ((margin.abs() > 4) & (margin.abs() <= 9)).astype(float) * 1.5
    score += ((robustness > 0.0) & (robustness < 0.75)).astype(float) * 1.5
    score += (((margin < 0) & (stability >= 0.8)) | ((margin > 0) & (stability < 0.6))).astype(float) * 2.0
    score += overlap.astype(float) * 1.5

    reference = bank["hidden_reference_status"].astype(str).str.lower()
    recommendation = bank.get("algorithmic_recommendation", "").astype(str).str.lower()
    recommendation_conflict = (
        (reference.eq("supported") & recommendation.eq("reject"))
        | (reference.ne("supported") & recommendation.eq("accept"))
    )
    score += recommendation_conflict.astype(float) * 2.0
    return score


def _select_challenging_cases(
    bank: pd.DataFrame,
    participant_id: str,
    count: int,
    global_seed: int,
) -> pd.DataFrame:
    """Select a diverse trio of difficult or ambiguous cases.

    The exact same three records are later repeated in every condition. This
    supports direct within-person comparisons of decisions on the same signal.
    """
    if count <= 0:
        raise ValueError("count must be positive")

    pool = bank[bank["pilot_ready"].astype(bool)].copy()
    pool = pool[~pool["hidden_case_category"].astype(str).str.startswith("clear_")].copy()
    if len(pool) < count:
        raise ValueError(f"Not enough challenging cases: need {count}, found {len(pool)}")

    pool["challenge_score"] = _challenge_score(pool)
    cohort, group = participant_counterbalance(participant_id, global_seed)
    # Prefer a mixed source trio. Alternate 2/1 split across stable cohorts.
    source_targets = {"synthetic": 2, "real": 1} if (cohort + group) % 2 == 0 else {"synthetic": 1, "real": 2}

    selected_rows: list[pd.Series] = []
    used_pairs: set[str] = set()
    used_categories: set[str] = set()

    def choose_from(source: str, target: int) -> None:
        """Choose difficult cases from one source while favoring category diversity."""
        candidates = pool[pool["source_type"].astype(str) == source].copy()
        if candidates.empty:
            return
        # Deterministic tie-breaking rotates exposure across participants.
        candidates["tie_break"] = candidates["case_id"].astype(str).map(
            lambda case_id: stable_int(f"{global_seed}|{participant_id}|{case_id}") % 1_000_000
        )
        candidates = candidates.sort_values(["challenge_score", "tie_break"], ascending=[False, True])

        # First pass favors distinct categories and matched pairs.
        for _, row in candidates.iterrows():
            if len([item for item in selected_rows if str(item["source_type"]) == source]) >= target:
                break
            pair_id = str(row["pair_id"])
            category = str(row["hidden_case_category"])
            if pair_id in used_pairs or category in used_categories:
                continue
            selected_rows.append(row)
            used_pairs.add(pair_id)
            used_categories.add(category)

        # Second pass relaxes category diversity but preserves unique pairs.
        for _, row in candidates.iterrows():
            if len([item for item in selected_rows if str(item["source_type"]) == source]) >= target:
                break
            pair_id = str(row["pair_id"])
            if pair_id in used_pairs:
                continue
            selected_rows.append(row)
            used_pairs.add(pair_id)
            used_categories.add(str(row["hidden_case_category"]))

    for source, target in source_targets.items():
        choose_from(source, target)

    if len(selected_rows) < count:
        remaining = pool.copy()
        remaining["tie_break"] = remaining["case_id"].astype(str).map(
            lambda case_id: stable_int(f"fallback|{global_seed}|{participant_id}|{case_id}") % 1_000_000
        )
        remaining = remaining.sort_values(["challenge_score", "tie_break"], ascending=[False, True])
        for _, row in remaining.iterrows():
            if len(selected_rows) >= count:
                break
            pair_id = str(row["pair_id"])
            if pair_id in used_pairs:
                continue
            selected_rows.append(row)
            used_pairs.add(pair_id)

    if len(selected_rows) < count:
        raise ValueError(f"Could not select {count} distinct challenging cases")

    selected = pd.DataFrame([row.to_dict() for row in selected_rows[:count]])
    # Order the trio from visually subtle to structurally complicated. The order
    # is fixed across all three conditions for the participant.
    category = selected["hidden_case_category"].astype(str)
    selected["slot_priority"] = np.select(
        [
            category.str.contains("near_boundary|low_detectability", case=False, regex=True),
            category.str.contains("overlap|duplicate|shoulder", case=False, regex=True),
            category.str.contains("unstable|parameter_sensitive|stable_unsupported", case=False, regex=True),
        ],
        [1, 2, 3],
        default=4,
    )
    selected = selected.sort_values(["slot_priority", "challenge_score"], ascending=[True, False]).reset_index(drop=True)
    selected["case_slot"] = range(1, count + 1)
    return selected.drop(columns=["slot_priority"], errors="ignore")


def assign_cases(
    case_bank: pd.DataFrame,
    participant_id: str,
    enabled_conditions: Iterable[str],
    total_trials: int = 9,
    global_seed: int = 20260805,
    trials_per_condition: int = 3,
) -> pd.DataFrame:
    """Assign one challenging case trio and repeat it across all enabled conditions.

    The function enforces the fixed condition order, three cases per condition,
    unique case pairs, and the explicit AI-accept recommendation in the final
    recommendation condition.
    """
    enabled = condition_order(participant_id, list(enabled_conditions), global_seed)
    if not enabled:
        raise ValueError("At least one condition must be enabled")
    if total_trials != len(enabled) * trials_per_condition:
        raise ValueError(
            "total_trials must equal enabled condition count × trials_per_condition "
            f"({len(enabled)} × {trials_per_condition} = {len(enabled) * trials_per_condition})"
        )

    selected = _select_challenging_cases(
        case_bank.copy(), participant_id, trials_per_condition, global_seed
    )

    rows: list[dict] = []
    trial_position = 1
    for block_number, condition in enumerate(enabled, start=1):
        for _, row in selected.sort_values("case_slot").iterrows():
            item = row.to_dict()
            item["condition"] = condition
            item["block_number"] = block_number
            item["condition_order"] = ">".join(enabled)
            item["trial_position"] = trial_position
            item["trial_id"] = f"{participant_id}-{trial_position:03d}"
            # The recommendation manipulation is deliberately explicit and
            # constant: the AI marks the candidate as a peak.
            item["displayed_recommendation"] = "Accept" if condition == CONDITION_RECOMMENDATION else ""
            rows.append(item)
            trial_position += 1

    assigned = pd.DataFrame(rows)
    counts = assigned["condition"].value_counts().to_dict()
    for condition in enabled:
        if counts.get(condition, 0) != trials_per_condition:
            raise AssertionError(
                f"Condition {condition} received {counts.get(condition, 0)} cases; expected {trials_per_condition}"
            )

    # Exactly three unique signals are repeated once in each condition.
    if assigned["case_id"].nunique() != trials_per_condition:
        raise AssertionError("Expected exactly one shared case trio across conditions")
    for slot, group in assigned.groupby("case_slot"):
        if group["case_id"].nunique() != 1 or len(group) != len(enabled):
            raise AssertionError(f"Case slot {slot} is not repeated consistently across conditions")
    if len(assigned) != total_trials:
        raise AssertionError(f"Expected {total_trials} trials, created {len(assigned)}")
    return assigned


def explanation_trial_ids(assignment: pd.DataFrame, count: int = 2) -> set[str]:
    """Choose a small number of explanation checks from evidence-bearing views."""
    eligible = assignment.loc[
        assignment["condition"].isin([CONDITION_EVIDENCE, CONDITION_RECOMMENDATION])
        & assignment.get("explanation_trial_eligible", True).astype(bool)
    ].copy()
    if eligible.empty or count <= 0:
        return set()

    selected: list[str] = []
    for condition in (CONDITION_EVIDENCE, CONDITION_RECOMMENDATION):
        group = eligible.loc[eligible["condition"] == condition].copy()
        if group.empty:
            continue
        group["has_conflict"] = group["hidden_disagreement_type"].astype(str).ne("none").astype(int)
        group = group.sort_values(["has_conflict", "case_slot"], ascending=[False, True])
        selected.append(str(group.iloc[0]["trial_id"]))
        if len(selected) >= count:
            return set(selected)

    for trial_id in eligible.sort_values("trial_position")["trial_id"].astype(str):
        if trial_id not in selected:
            selected.append(trial_id)
        if len(selected) >= count:
            break
    return set(selected)
