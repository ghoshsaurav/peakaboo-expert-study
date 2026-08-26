from __future__ import annotations

import os
from typing import Any

import pandas as pd
import plotly.express as px
import streamlit as st

from .config import Paths
from .data_loader import load_case_bank, load_signal_bundle
from .logging_store import StudyStore
from .metrics import (
    analysis_ready_trials,
    condition_summary,
    conflict_summary,
    descriptive_summary,
    evidence_frequency,
    reliance_summary,
    same_case_decision_changes,
)
from .questionnaires import TERM_HELP
from .visualization import chromatogram_figure, detectability_figure, parameter_robustness_figure, stability_figure


def _csv_bytes(frame: pd.DataFrame) -> bytes:
    return frame.to_csv(index=False).encode("utf-8")


def _authenticate(config: dict[str, Any]) -> bool:
    expected = os.getenv("PEAKABOO_RESEARCHER_PASSWORD", str(config.get("researcher", {}).get("password", "change-me")))
    if st.session_state.get("researcher_authenticated"):
        return True
    st.header("Researcher access")
    st.caption("Use the sidebar glossary (?) for definitions of study terms.")
    password = st.text_input("Researcher password", type="password", help="Change the default password before deployment.")
    if st.button("Unlock researcher mode", type="primary"):
        if password == expected:
            st.session_state["researcher_authenticated"] = True
            st.rerun()
        else:
            st.error("Incorrect password.")
    return False


def _load_results(store: StudyStore) -> tuple[pd.DataFrame, pd.DataFrame, pd.DataFrame, pd.DataFrame]:
    sessions = store.table("sessions")
    assignments = store.table("assignments")
    responses = store.table("trial_responses")
    surveys = store.table("survey_responses")
    trials = analysis_ready_trials(assignments, responses)
    return sessions, surveys, responses, trials


def render_overview(store: StudyStore) -> None:
    sessions, _, _, trials = _load_results(store)
    summary = descriptive_summary(trials)
    columns = st.columns(6)
    columns[0].metric("Sessions", len(sessions), help="All started participant sessions.")
    columns[1].metric(
        "Completed sessions",
        int((sessions.get("status", "") == "complete").sum()) if not sessions.empty else 0,
    )
    columns[2].metric("Completed decisions", summary["completed_trials"], help="Maximum of nine per participant.")
    columns[3].metric("Participants with decisions", summary["participants"])
    columns[4].metric(
        "Reference alignment",
        f"{summary['reference_alignment_rate']:.1%}" if pd.notna(summary.get("reference_alignment_rate")) else "—",
        help=TERM_HELP["reference"],
    )
    columns[5].metric(
        "Calibration error",
        f"{summary['mean_calibration_error']:.2f}" if pd.notna(summary.get("mean_calibration_error")) else "—",
        help="Lower values mean reported confidence better matches reference alignment.",
    )
    st.info(
        "The study uses the same three difficult cases in a fixed order: signal only, separate evidence, then an explicit AI peak mark."
    )
    if sessions.empty:
        st.info("No participant sessions have been recorded.")
        return
    st.dataframe(sessions.sort_values("started_at", ascending=False), use_container_width=True)


def _apply_filters(trials: pd.DataFrame) -> pd.DataFrame:
    st.subheader("Filters")
    filters = st.columns(4)
    conditions = sorted(trials["condition"].dropna().astype(str).unique())
    selected_conditions = filters[0].multiselect("Condition (?)", conditions, default=conditions, help="The three study views.")
    sources = sorted(trials.get("source_type", pd.Series(dtype=str)).dropna().astype(str).unique())
    selected_sources = filters[1].multiselect("Source", sources, default=sources)
    categories = sorted(trials.get("hidden_case_category", pd.Series(dtype=str)).dropna().astype(str).unique())
    selected_categories = filters[2].multiselect("Case category (?)", categories, default=categories, help="Researcher-coded failure-mode category.")
    disagreements = sorted(trials.get("hidden_disagreement_type", pd.Series(dtype=str)).dropna().astype(str).unique())
    selected_disagreements = filters[3].multiselect(
        "Evidence conflict (?)",
        disagreements,
        default=disagreements,
        help="Hidden case metadata describing whether evidence sources were designed to agree or conflict.",
    )

    filtered = trials.copy()
    if selected_conditions:
        filtered = filtered[filtered["condition"].astype(str).isin(selected_conditions)]
    if selected_sources and "source_type" in filtered:
        filtered = filtered[filtered["source_type"].astype(str).isin(selected_sources)]
    if selected_categories and "hidden_case_category" in filtered:
        filtered = filtered[filtered["hidden_case_category"].astype(str).isin(selected_categories)]
    if selected_disagreements and "hidden_disagreement_type" in filtered:
        filtered = filtered[filtered["hidden_disagreement_type"].astype(str).isin(selected_disagreements)]
    return filtered


def render_results(store: StudyStore) -> None:
    _, surveys, _, trials = _load_results(store)
    if trials.empty or trials["decision_code"].notna().sum() == 0:
        st.info("No completed trial responses are available.")
        return

    filtered = _apply_filters(trials)
    summary = descriptive_summary(filtered)
    columns = st.columns(6)
    columns[0].metric("Decisions", summary["completed_trials"])
    columns[1].metric("Accept", f"{summary['accept_rate']:.1%}")
    columns[2].metric("Reject", f"{summary['reject_rate']:.1%}")
    columns[3].metric("Defer (?)", f"{summary['defer_rate']:.1%}", help=TERM_HELP["defer"])
    columns[4].metric(
        "Reference aligned (?)",
        f"{summary['reference_alignment_rate']:.1%}" if pd.notna(summary.get("reference_alignment_rate")) else "—",
        help=TERM_HELP["reference"],
    )
    columns[5].metric(
        "Unsupported accepted",
        f"{summary['unsupported_acceptance_rate']:.1%}" if pd.notna(summary["unsupported_acceptance_rate"]) else "—",
    )

    st.subheader("RQ2 — How decomposed evidence changes decisions")
    by_condition = condition_summary(filtered)
    if not by_condition.empty:
        st.dataframe(by_condition, use_container_width=True)
        long = by_condition.melt(
            id_vars=["condition"],
            value_vars=["accept_rate", "reject_rate", "defer_rate"],
            var_name="decision",
            value_name="rate",
        )
        st.plotly_chart(
            px.bar(long, x="condition", y="rate", color="decision", barmode="group", title="Decision rates by condition"),
            use_container_width=True,
        )
        outcome_long = by_condition.melt(
            id_vars=["condition"],
            value_vars=["reference_alignment_rate", "mean_calibration_error", "mean_response_time_seconds"],
            var_name="outcome",
            value_name="value",
        )
        st.dataframe(outcome_long, use_container_width=True)

    st.subheader("Direct comparison of the same three cases")
    paired = same_case_decision_changes(filtered)
    if paired.empty:
        st.caption("Same-case comparisons appear after participants complete all three views.")
    else:
        change_columns = [
            column for column in [
                "changed_after_evidence",
                "changed_after_ai_peak_mark",
                "changed_from_baseline_to_ai",
            ]
            if column in paired.columns
        ]
        if change_columns:
            summary_rows = [
                {
                    "comparison": column.replace("_", " "),
                    "change_rate": float(pd.to_numeric(paired[column], errors="coerce").mean()),
                    "n_shared_cases": int(pd.to_numeric(paired[column], errors="coerce").notna().sum()),
                }
                for column in change_columns
            ]
            st.dataframe(pd.DataFrame(summary_rows), use_container_width=True, hide_index=True)
        st.dataframe(paired, use_container_width=True, hide_index=True)
        st.download_button(
            "Download same-case comparison table",
            _csv_bytes(paired),
            "same_case_decision_changes.csv",
            "text/csv",
        )

    st.subheader("RQ2/RQ3 — Which evidence people used")
    evidence = evidence_frequency(filtered)
    if evidence.empty:
        st.caption("No evidence-use responses are available.")
    else:
        st.plotly_chart(px.bar(evidence, x="count", y="evidence", orientation="h"), use_container_width=True)
        st.dataframe(evidence, use_container_width=True)

    st.subheader("RQ3 — Evidence conflict and confusion")
    conflicts = conflict_summary(filtered)
    if conflicts.empty:
        st.caption("Conflict summaries require completed trials with case conflict metadata.")
    else:
        st.dataframe(conflicts, use_container_width=True)
        conflict_long = conflicts.melt(
            id_vars=["condition", "case_has_evidence_conflict"],
            value_vars=["defer_rate", "reference_alignment_rate", "mean_clarity"],
            var_name="outcome",
            value_name="value",
        )
        st.plotly_chart(
            px.bar(
                conflict_long,
                x="condition",
                y="value",
                color="case_has_evidence_conflict",
                facet_col="outcome",
                barmode="group",
                title="Agreement versus conflict cases",
            ),
            use_container_width=True,
        )

    st.subheader("RQ4 — Recommendation reliance")
    reliance = reliance_summary(filtered)
    if reliance.empty:
        st.caption("Reliance categories appear after evidence-plus-recommendation trials are completed.")
    else:
        st.dataframe(reliance, use_container_width=True)
        st.plotly_chart(
            px.bar(reliance, x="reliance_category", y="rate", text="count", title="Reliance categories"),
            use_container_width=True,
        )
        st.caption(
            "Over-reliance means the participant followed a recommendation that disagreed with the reference comparison. "
            "This is not the same as proving chemical error."
        )

    st.subheader("Questionnaire summaries")
    if surveys.empty:
        st.caption("No questionnaire responses are available.")
    else:
        survey_distribution = (
            surveys.groupby(["section", "question_code", "response_label"], dropna=False)
            .size()
            .reset_index(name="count")
            .sort_values(["section", "question_code", "count"], ascending=[True, True, False])
        )
        selected_section = st.selectbox(
            "Questionnaire section (?)",
            sorted(survey_distribution["section"].astype(str).unique()),
            key="researcher_survey_section",
            help="Background, current practice, comprehension, condition checks, or final questions.",
        )
        st.dataframe(
            survey_distribution[survey_distribution["section"].astype(str) == selected_section],
            use_container_width=True,
        )

    st.download_button(
        "Download filtered analysis table",
        _csv_bytes(filtered),
        "peakaboo_analysis_filtered.csv",
        "text/csv",
    )


def render_case_bank(bank: pd.DataFrame, paths: Paths) -> None:
    st.subheader("Case bank")
    st.caption("Hidden comparison labels and case categories are visible only in researcher mode.")
    filter_columns = st.columns(4)
    source = filter_columns[0].multiselect("Source type", sorted(bank["source_type"].unique()), default=sorted(bank["source_type"].unique()))
    category = filter_columns[1].multiselect(
        "Category (?)",
        sorted(bank["hidden_case_category"].astype(str).unique()),
        default=sorted(bank["hidden_case_category"].astype(str).unique()),
        help="Researcher-coded candidate type or detector failure mode.",
    )
    disagreement = filter_columns[2].multiselect(
        "Conflict type (?)",
        sorted(bank["hidden_disagreement_type"].astype(str).unique()),
        default=sorted(bank["hidden_disagreement_type"].astype(str).unique()),
        help="The evidence sources expected to agree or conflict in this case.",
    )
    pilot_only = filter_columns[3].checkbox("Pilot-ready only", value=True)
    filtered = bank[
        bank["source_type"].isin(source)
        & bank["hidden_case_category"].astype(str).isin(category)
        & bank["hidden_disagreement_type"].astype(str).isin(disagreement)
    ].copy()
    if pilot_only:
        filtered = filtered[filtered["pilot_ready"].astype(bool)]
    st.dataframe(filtered, use_container_width=True, height=360)

    with st.expander("Edit pilot metadata"):
        editable_columns = [
            "case_id",
            "pilot_ready",
            "explanation_trial_eligible",
            "hidden_case_category",
            "hidden_disagreement_type",
        ]
        editable = st.data_editor(
            bank[editable_columns].copy(),
            disabled=["case_id"],
            hide_index=True,
            use_container_width=True,
            key="case_bank_metadata_editor",
        )
        if st.button("Save case-bank metadata"):
            updated = bank.copy().set_index("case_id")
            changes = editable.set_index("case_id")
            for column in editable_columns[1:]:
                updated.loc[changes.index, column] = changes[column]
            updated.reset_index().to_csv(paths.case_bank, index=False)
            load_case_bank.cache_clear()
            st.success("Case-bank metadata saved.")
            st.rerun()

    if filtered.empty:
        return
    selected = st.selectbox("Preview case", filtered["case_id"].astype(str).tolist())
    case = filtered.loc[filtered["case_id"].astype(str) == selected].iloc[0].to_dict()
    bundle = load_signal_bundle(paths.signals, str(case["signal_key"]))
    columns = st.columns([2, 1])
    with columns[0]:
        st.plotly_chart(
            chromatogram_figure(bundle, show_variation_band=True, title=f"Researcher preview: {selected}"),
            use_container_width=True,
        )
    with columns[1]:
        st.json(
            {
                "reference_status": case["hidden_reference_status"],
                "category": case["hidden_case_category"],
                "disagreement": case["hidden_disagreement_type"],
                "recommendation": case["algorithmic_recommendation"],
                "detectability": case["detectability"],
                "margin": case["weber_margin"],
                "stability": case["stability"],
                "parameter_robustness": case["parameter_robustness"],
                "duplicate_risk": case["duplicate_risk"],
            }
        )
    detail_columns = st.columns(3)
    with detail_columns[0]:
        st.plotly_chart(detectability_figure(float(case["detectability"]), float(case["weber_boundary"])), use_container_width=True)
    with detail_columns[1]:
        st.plotly_chart(stability_figure(bundle.stability_hits), use_container_width=True)
    with detail_columns[2]:
        st.plotly_chart(
            parameter_robustness_figure(bundle.parameter_matrix, bundle.parameter_smoothing, bundle.parameter_k),
            use_container_width=True,
        )
    st.download_button("Download case bank CSV", _csv_bytes(bank), "case_bank.csv", "text/csv")


def render_exports(store: StudyStore, paths: Paths) -> None:
    st.subheader("Data exports")
    sessions, surveys, responses, trials = _load_results(store)
    assignments = store.table("assignments")
    columns = st.columns(2)
    columns[0].download_button("Sessions CSV", _csv_bytes(sessions), "sessions.csv", "text/csv")
    columns[1].download_button("Assignments CSV", _csv_bytes(assignments), "assignments.csv", "text/csv")
    columns[0].download_button("Survey responses CSV", _csv_bytes(surveys), "survey_responses.csv", "text/csv")
    columns[1].download_button("Trial responses CSV", _csv_bytes(responses), "trial_responses.csv", "text/csv")
    st.download_button("Analysis-ready trial table", _csv_bytes(trials), "analysis_ready_trials.csv", "text/csv")
    if store.is_sqlite and paths.database.exists():
        st.download_button("SQLite database", paths.database.read_bytes(), "study.db", "application/octet-stream")
    st.markdown(
        "The analysis-ready table contains reference-alignment, calibration, evidence-conflict, and reliance-category fields. "
        "Reference correspondence remains comparison evidence rather than chemical truth."
    )


def render_researcher_mode(config: dict[str, Any], paths: Paths, bank: pd.DataFrame, store: StudyStore) -> None:
    if not _authenticate(config):
        return
    st.title("Peak-a-boo researcher dashboard")
    st.caption("The participant flow uses plain wording and clickable ? definitions. Order is fixed and the same three cases repeat across views.")
    tabs = st.tabs(["Study status", "RQ results", "Case bank", "Exports"])
    with tabs[0]:
        render_overview(store)
    with tabs[1]:
        render_results(store)
    with tabs[2]:
        render_case_bank(bank, paths)
    with tabs[3]:
        render_exports(store, paths)
