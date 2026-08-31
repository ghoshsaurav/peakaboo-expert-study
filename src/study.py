"""Participant-facing workflow for the three-condition Peak-a-boo expert study."""

from __future__ import annotations

import time
from typing import Any

import pandas as pd
import streamlit as st

from .assignment import (
    CONDITION_BASELINE,
    CONDITION_EVIDENCE,
    CONDITION_RECOMMENDATION,
    assign_cases,
    condition_order,
    explanation_trial_ids,
)
from .config import Paths
from .data_loader import load_signal_bundle, parse_provenance
from .logging_store import StudyStore
from .models import participant_case
from .questionnaires import (
    BASELINE_EVIDENCE_OPTIONS,
    COMPREHENSION_ITEMS,
    CURRENT_PRACTICE_EVIDENCE,
    DECISION_OPTIONS,
    DEFERRAL_REASONS,
    DISTRUST_OPTIONS,
    ERROR_COST_OPTIONS,
    EXPERIENCE_OPTIONS,
    EXPLANATION_OPTIONS,
    FINAL_CONDITION_LABELS,
    PEAKABOO_EVIDENCE_OPTIONS,
    POST_CONDITION_ITEMS,
    REVIEW_FREQUENCY_OPTIONS,
    ROLE_OPTIONS,
    TERM_HELP,
    TERM_LABELS,
    machine_code,
)
from .visualization import (
    chromatogram_figure,
    detectability_figure,
    parameter_robustness_figure,
    stability_figure,
)


def render_key_terms(term_keys: list[str] | None = None) -> None:
    """Show clickable plain-language help consistently on participant pages."""
    keys = term_keys or [
        "candidate",
        "chromatogram",
        "raw_signal",
        "smoothed_signal",
        "detectability",
        "decision_boundary",
        "perturbation",
        "stability",
        "parameter_robustness",
        "overlap",
        "duplicate",
        "defer",
        "recommendation",
    ]
    keys = [key for key in keys if key in TERM_HELP]
    st.caption("Tap a ? button whenever a study word is unclear.")
    with st.expander("Quick word help (?)", expanded=False):
        columns = st.columns(3)
        for index, key in enumerate(keys):
            with columns[index % 3]:
                with st.popover(f"? {TERM_LABELS.get(key, key.replace('_', ' ').title())}"):
                    st.write(TERM_HELP[key])


def _save_multi(store: StudyStore, session_id: str, section: str, code: str, values: list[str]) -> None:
    """Save a multi-select questionnaire response in coded, labeled, and JSON forms."""
    store.save_survey_response(
        session_id=session_id,
        section=section,
        question_code=code,
        response_code="|".join(machine_code(value) for value in values),
        response_label=" | ".join(values),
        response=values,
    )


def _save_single(store: StudyStore, session_id: str, section: str, code: str, value: Any) -> None:
    """Save one questionnaire response with a stable machine code and display label."""
    store.save_survey_response(
        session_id=session_id,
        section=section,
        question_code=code,
        response_code=machine_code(str(value)),
        response_label=value,
        response=value,
    )


def _section_complete(response_map: dict[tuple[str, str], dict[str, Any]], section: str, sentinel: str) -> bool:
    """Check whether the sentinel response marking one survey section complete is present."""
    return (section, sentinel) in response_map


def _initialize_participant(
    participant_id: str,
    config: dict[str, Any],
    bank: pd.DataFrame,
    store: StudyStore,
) -> tuple[str, pd.DataFrame]:
    """Create or resume a participant session and persist its deterministic assignment."""
    enabled_conditions = list(config["study"]["enabled_conditions"])
    order = condition_order(participant_id, enabled_conditions, int(config["study"]["global_seed"]))
    session_id = store.get_or_create_session(
        participant_id=participant_id,
        condition_order=">".join(order),
        case_bank_version=str(config["study"]["case_bank_version"]),
        study_version=str(config["study"]["study_version"]),
    )
    assignment = store.assignment_for_session(session_id)
    if assignment.empty:
        assignment = assign_cases(
            bank,
            participant_id=participant_id,
            enabled_conditions=enabled_conditions,
            total_trials=int(config["study"]["trials_per_participant"]),
            trials_per_condition=int(config["study"]["trials_per_condition"]),
            global_seed=int(config["study"]["global_seed"]),
        )
        store.save_assignments(session_id, assignment)
    st.session_state["participant_id"] = participant_id
    st.session_state["session_id"] = session_id
    return session_id, assignment


def render_entry(config: dict[str, Any], bank: pd.DataFrame, store: StudyStore) -> None:
    """Render participant ID, consent, and begin/resume controls."""
    st.title(config["study"]["title"])
    render_key_terms()
    st.write(
        "You will make nine decisions in a fixed order: three signal-only decisions, then three decisions with "
        "separate evidence, and finally three decisions where the AI clearly says the candidate is a peak."
    )
    st.info(
        "The same three chromatograms appear in all three views. Case 1 matches Case 1, Case 2 matches Case 2, "
        "and Case 3 matches Case 3, so changes in your judgment can be compared directly."
    )
    st.info(
        "For each marked bump, choose Accept, Reject, or Defer. The study comparison answer stays hidden until "
        "all nine decisions are complete, so it cannot influence later views of the same signal."
    )
    participant_id = st.text_input(
        "Participant ID",
        help="Use the ID assigned by the researcher. Do not enter your name.",
    )
    consent = st.checkbox("I have reviewed the study information and agree to continue.")
    if st.button("Begin or resume study", type="primary", disabled=not (participant_id.strip() and consent)):
        _initialize_participant(participant_id.strip(), config, bank, store)
        st.rerun()


def render_background(session_id: str, store: StudyStore) -> None:
    """Collect non-identifying background and chromatography-experience information."""
    st.header("About your experience")
    render_key_terms()
    st.caption("These questions describe the participant group. They do not ask for identifying information.")
    with st.form("background_form"):
        role = st.selectbox("Your main role", ROLE_OPTIONS)
        experience = st.selectbox("Years of chromatography experience", EXPERIENCE_OPTIONS)
        review_frequency = st.selectbox("How often do you review chromatograms (?)?", REVIEW_FREQUENCY_OPTIONS, help=TERM_HELP["chromatogram"])
        automated_detection = st.slider(
            "Experience using software that marks possible peaks (?)",
            1,
            5,
            3,
            help="1 = none; 5 = a lot of experience. " + TERM_HELP["detector"],
        )
        uncertainty_familiarity = st.slider(
            "Experience using information about how unsure a result may be (?)",
            1,
            5,
            2,
            help="1 = none; 5 = a lot of experience. This includes scores, ranges, or warnings that show uncertainty.",
        )
        decision_responsibility = st.radio(
            "Do you normally make or review final peak decisions (?)?",
            ["Yes", "Sometimes", "No"],
            horizontal=True,
            help=TERM_HELP["peak"],
        )
        submitted = st.form_submit_button("Save and continue", type="primary")
    if submitted:
        values = {
            "role": role,
            "chromatography_experience": experience,
            "review_frequency": review_frequency,
            "automated_detection_experience": automated_detection,
            "uncertainty_familiarity": uncertainty_familiarity,
            "decision_responsibility": decision_responsibility,
        }
        for code, value in values.items():
            _save_single(store, session_id, "background", code, value)
        _save_single(store, session_id, "background", "completed", "yes")
        store.update_progress(session_id, "current_practice")
        st.rerun()


def render_current_practice(session_id: str, store: StudyStore) -> None:
    """Collect formative information about how the participant currently reviews difficult peaks."""
    st.header("How you review peaks now")
    render_key_terms()
    st.write("These questions examine how analysts currently review difficult candidates.")
    with st.form("current_practice_form"):
        evidence = st.multiselect(
            "Which information do you normally use? Choose up to three.",
            CURRENT_PRACTICE_EVIDENCE,
            max_selections=3,
            help="Choose the information that most often affects your decision.",
        )
        first_evidence = st.selectbox(
            "Which information do you usually check first?",
            CURRENT_PRACTICE_EVIDENCE + ["It depends on the case"],
        )
        deferral = st.multiselect(
            "What usually makes you wait for more review (?)? Choose up to two.",
            DEFERRAL_REASONS,
            max_selections=2,
            help=TERM_HELP["defer"],
        )
        cost = st.radio("Which error is usually more costly?", ERROR_COST_OPTIONS)
        current_uncertainty = st.radio(
            "Does your current software explain why a marked peak may be doubtful (?)?",
            ["Yes", "Partly", "No"],
            horizontal=True,
            help=TERM_HELP["evidence"],
        )
        distrust = st.multiselect(
            "What makes you question the peak-marking software (?)? Choose up to two.",
            DISTRUST_OPTIONS,
            max_selections=2,
            help=TERM_HELP["detector"],
        )
        missing_info = st.text_input(
            "Optional: What important information is missing from your current software?",
            max_chars=250,
        )
        submitted = st.form_submit_button("Save and continue", type="primary")
    if submitted:
        if not evidence:
            st.error("Select at least one type of information you normally use.")
            return
        _save_multi(store, session_id, "current_practice", "evidence_normally_used", evidence)
        _save_single(store, session_id, "current_practice", "first_evidence", first_evidence)
        _save_multi(store, session_id, "current_practice", "deferral_reasons", deferral)
        _save_single(store, session_id, "current_practice", "costlier_error", cost)
        _save_single(store, session_id, "current_practice", "current_uncertainty_support", current_uncertainty)
        _save_multi(store, session_id, "current_practice", "distrust_reasons", distrust)
        _save_single(store, session_id, "current_practice", "missing_information_text", missing_info.strip())
        _save_single(store, session_id, "current_practice", "completed", "yes")
        store.update_progress(session_id, "tutorial")
        st.rerun()


def render_tutorial(session_id: str, store: StudyStore) -> None:
    """Teach the evidence terms, administer four practice questions, and show the answer key."""
    st.header("Quick guide and four practice questions")
    render_key_terms()
    st.markdown(
        "The separate-evidence view gives several clues instead of one final score. "
        "One clue shows how clearly the bump rises above noise. Another checks whether the software finds it again "
        "after small signal changes. Another checks small setting changes. Shape warnings show possible overlap or duplicates."
    )
    st.warning(
        "No single clue proves that a chemical peak is real. When clues point in different directions, waiting for more review can be reasonable."
    )

    with st.form("comprehension_form"):
        answers: dict[str, str] = {}
        for item in COMPREHENSION_ITEMS:
            help_text = " ".join(TERM_HELP[key] for key in item.get("help_terms", []) if key in TERM_HELP)
            answers[item["code"]] = st.radio(
                item["prompt"],
                item["options"],
                key=f"comp_{item['code']}",
                help=help_text or None,
            )
        submitted = st.form_submit_button("Check answers", type="primary")

    if submitted:
        correct_count = 0
        result_rows: list[dict[str, Any]] = []
        for item in COMPREHENSION_ITEMS:
            answer = answers[item["code"]]
            correct = answer == item["correct"]
            correct_count += int(correct)
            result_rows.append({"item": item, "selected": answer, "correct": correct})
            store.save_survey_response(
                session_id,
                "comprehension",
                item["code"],
                response_code=machine_code(answer),
                response_label=answer,
                response={"selected": answer, "correct_answer": item["correct"], "correct": correct},
            )
        store.save_survey_response(
            session_id,
            "comprehension",
            "score",
            response_code=str(correct_count),
            response_label=f"{correct_count}/{len(COMPREHENSION_ITEMS)}",
            response={"score": correct_count, "total": len(COMPREHENSION_ITEMS)},
        )
        st.session_state["comprehension_result"] = {
            "score": correct_count,
            "total": len(COMPREHENSION_ITEMS),
            "rows": result_rows,
        }

    result = st.session_state.get("comprehension_result")
    if result:
        st.divider()
        st.subheader("Answer key")
        st.write(f"Score: **{result['score']} of {result['total']}**")
        for index, row in enumerate(result["rows"], start=1):
            item = row["item"]
            symbol = "Correct" if row["correct"] else "Review"
            st.markdown(
                f"**{index}. {symbol}**  \n"
                f"Your answer: {row['selected']}  \n"
                f"Correct answer: **{item['correct']}**  \n"
                f"{item['explanation']}"
            )
        st.info("The answer key is shown here so the evidence terms are clear before candidate review.")
        if st.button("Continue to candidate reviews", type="primary"):
            _save_single(store, session_id, "comprehension", "completed", "yes")
            store.update_progress(session_id, "trials")
            st.session_state.pop("comprehension_result", None)
            st.rerun()


def _interpret_case(case: dict[str, Any]) -> dict[str, str]:
    """Convert numeric evidence values into participant-facing plain-language summaries."""
    margin = float(case["weber_margin"])
    stability = float(case["stability"])
    robustness = float(case["parameter_robustness"])
    return {
        "detectability": "Clearly above cutoff" if margin > 3 else "Clearly below cutoff" if margin < -3 else "Close to cutoff",
        "stability": "Usually found again" if stability >= 0.8 else "Sometimes found again" if stability >= 0.5 else "Often disappears",
        "robustness": "Usually stays marked" if robustness >= 0.75 else "Sometimes stays marked" if robustness >= 0.5 else "Often changes",
        "structure": "Possible overlap or duplicate" if bool(case.get("overlap_flag", False)) else "No strong shape warning",
    }


def render_peakaboo_evidence(case: dict[str, Any], bundle: Any, condition: str) -> dict[str, bool]:
    """Render decomposed evidence and record which optional evidence sections were opened."""
    safe = participant_case(case)
    interpretations = _interpret_case(safe)
    if condition == CONDITION_RECOMMENDATION:
        st.error(
            "AI DECISION: PEAK. The AI is explicitly marking this candidate as a peak and recommends: ACCEPT AS A PEAK. "
            "This is direct AI advice, separate from the clues below, and it may be wrong.",
            icon="🤖",
        )
    st.subheader("Separate evidence")
    st.caption("Each clue answers a different question. A clue can be useful without proving that the peak is real.")

    columns = st.columns(4)
    columns[0].metric(
        "Stands out from noise (?)",
        f"{float(safe['detectability']):.2f}",
        f"Cutoff distance {float(safe['weber_margin']):+.2f}",
        delta_color="off",
        help=TERM_HELP["detectability"] + " " + TERM_HELP["boundary_margin"],
    )
    columns[1].metric(
        "Same after signal changes (?)",
        f"{int(safe['stability_hits'])}/{int(safe['stability_runs'])}",
        help=TERM_HELP["perturbation"] + " " + TERM_HELP["stability"],
    )
    columns[2].metric(
        "Same after setting changes (?)",
        f"{int(safe['parameter_hits'])}/{int(safe['parameter_runs'])}",
        help=TERM_HELP["parameter"] + " " + TERM_HELP["parameter_robustness"],
    )
    columns[3].metric(
        "Overlap or duplicate warning (?)",
        str(safe["duplicate_risk"]),
        help=TERM_HELP["overlap"] + " " + TERM_HELP["duplicate"],
    )

    st.markdown(
        f"**Do the clues point the same way?** {safe['evidence_agreement']}  \n"
        f"Stands out from noise: {interpretations['detectability']} · "
        f"Same after signal changes: {interpretations['stability']} · "
        f"Same after setting changes: {interpretations['robustness']} · "
        f"Shape warning: {interpretations['structure']}"
    )

    st.plotly_chart(
        detectability_figure(float(safe["detectability"]), float(safe["weber_boundary"])),
        use_container_width=True,
    )
    st.caption(
        f"Rise above surroundings = {float(safe['prominence']):.4g}; nearby noise = {float(safe['local_noise']):.4g}. "
        "The bar compares how much the bump rises with the noise around it."
    )

    show_stability = st.checkbox(
        "Show small-signal-change test (?)",
        key=f"stability_detail_{safe['case_id']}_{condition}",
        help=TERM_HELP["perturbation"] + " " + TERM_HELP["stability"],
    )
    if show_stability:
        st.plotly_chart(stability_figure(bundle.stability_hits), use_container_width=True)
        st.caption("Each box is one test. A filled result means the software found the candidate again near the same location.")

    show_parameters = st.checkbox(
        "Show small-setting-change test (?)",
        key=f"parameter_detail_{safe['case_id']}_{condition}",
        help=TERM_HELP["parameter_robustness"],
    )
    if show_parameters:
        st.plotly_chart(
            parameter_robustness_figure(bundle.parameter_matrix, bundle.parameter_smoothing, bundle.parameter_k),
            use_container_width=True,
        )
        st.caption("Each box shows whether the candidate remained marked after a small change to normal software settings.")

    show_provenance = st.checkbox(
        "Show shape and processing details (?)",
        key=f"provenance_detail_{safe['case_id']}_{condition}",
        help=TERM_HELP["structural_ambiguity"] + " " + TERM_HELP["provenance"],
    )
    if show_provenance:
        st.write(
            {
                "Distance to nearest marked bump (data points)": round(float(safe["nearest_distance_samples"]), 2)
                if float(safe["nearest_distance_samples"]) < 1e9
                else "No nearby marked bump",
                "Bump width (data points)": round(float(safe["width_samples"]), 2),
                "Separation compared with width": round(float(safe["separation_width_ratio"]), 2)
                if float(safe["separation_width_ratio"]) < 1e9
                else "No nearby marked bump",
                "Possible overlap": bool(safe["overlap_flag"]),
                "Background-change score": round(float(safe["baseline_drift_score"]), 3),
                "Distance to processing-window edge": int(safe["segment_boundary_distance"]),
            }
        )
        st.json(parse_provenance(safe.get("provenance_json")))

    return {
        "stability_details": show_stability,
        "parameter_details": show_parameters,
        "provenance": show_provenance,
    }


def render_trial(
    session_id: str,
    assignment: pd.DataFrame,
    store: StudyStore,
    paths: Paths,
    explanation_ids: set[str],
) -> None:
    """Render the next incomplete review trial and save its decision and interaction record."""
    completed = store.completed_trial_ids(session_id)
    remaining = assignment.loc[~assignment["trial_id"].astype(str).isin(completed)].copy()
    if remaining.empty:
        return
    row = remaining.sort_values("trial_position").iloc[0].to_dict()
    safe = participant_case(row)
    trial_id = str(safe["trial_id"])
    condition = str(safe["condition"])
    bundle = load_signal_bundle(paths.signals, str(safe["signal_key"]))

    if f"trial_start_{trial_id}" not in st.session_state:
        st.session_state[f"trial_start_{trial_id}"] = time.time()
        store.log_event(session_id, "trial_opened", {"case_id": safe["case_id"], "condition": condition}, trial_id)

    condition_label = FINAL_CONDITION_LABELS.get(condition, condition)
    within_condition = int(safe.get("case_slot", 1))
    st.progress(int(safe["trial_position"]) / len(assignment), text=f"Decision {safe['trial_position']} of {len(assignment)}")
    st.header(condition_label)
    st.caption(f"Case {within_condition} of 3. This exact same chromatogram is used as Case {within_condition} in all three views.")
    render_key_terms()

    st.plotly_chart(
        chromatogram_figure(
            bundle,
            show_variation_band=condition != CONDITION_BASELINE,
            title=f"Case {within_condition}: same signal across all three views",
            show_nearby_maxima=condition != CONDITION_BASELINE,
        ),
        use_container_width=True,
    )
    if condition != CONDITION_BASELINE:
        st.caption(
            "The shaded area shows nearby signal variation. It is not a formal confidence interval. "
            "Tap the ? word-help buttons above for a short explanation."
        )
        opened = render_peakaboo_evidence(safe, bundle, condition)
    else:
        opened = {"stability_details": False, "parameter_details": False, "provenance": False}
        st.info("The diamond marks the bump selected by the peak-marking software. In this first view, use only the signal shape and nearby context.")

    evidence_options = list(BASELINE_EVIDENCE_OPTIONS if condition == CONDITION_BASELINE else PEAKABOO_EVIDENCE_OPTIONS)
    if condition == CONDITION_RECOMMENDATION:
        evidence_options.insert(-1, "AI says this is a peak")
    explanation_trial = trial_id in explanation_ids

    with st.form(f"trial_form_{trial_id}"):
        decision = st.radio(
            "How should this candidate be handled?",
            list(DECISION_OPTIONS),
            help=(
                "Accept means keep it as a peak. Reject means treat it as noise, an error, or a duplicate. "
                + TERM_HELP["defer"]
            ),
        )
        confidence = st.slider(
            "How confident are you?",
            0,
            100,
            50,
            help="0 = not confident; 100 = completely confident.",
        )
        primary_evidence = st.selectbox(
            "Which information influenced your answer most?",
            evidence_options,
            help="Choose the single most important reason for this decision.",
        )

        evidence_disagreement: str | None = None
        explanation_reason: list[str] = []
        clarity: int | None = None
        disagreement_sources: list[str] = []
        if condition != CONDITION_BASELINE:
            evidence_disagreement = st.radio(
                "Did any of the clues point in different directions (?)?",
                ["No", "Yes", "Unsure"],
                horizontal=True,
                help=TERM_HELP["evidence_conflict"] + " For example, the bump may stand out clearly but disappear after small signal changes.",
            )
        if explanation_trial and condition != CONDITION_BASELINE:
            st.markdown("#### Short explanation check")
            reason = st.selectbox(
                "What is the main reason this case may be hard to judge (?)?",
                EXPLANATION_OPTIONS,
                help="Choose the reason that best matches the clues shown above.",
            )
            explanation_reason = [reason]
            clarity = st.slider(
                "How clear was the uncertainty information?",
                1,
                5,
                3,
                help="1 = very unclear; 5 = very clear.",
            )
            if evidence_disagreement == "Yes":
                disagreement = st.selectbox(
                    "Which clues pointed in different directions?",
                    [
                        "How clearly it stands out and repeatability",
                        "The clues and the visible signal shape",
                        "The AI peak mark and my own judgment",
                        "Other or unsure",
                    ],
                )
                disagreement_sources = [disagreement]

        submitted = st.form_submit_button("Submit decision", type="primary")

    if submitted:
        recommendation = str(safe.get("displayed_recommendation") or "Accept") if condition == CONDITION_RECOMMENDATION else None
        followed = None
        if recommendation:
            mapping = {
                "Accept": "Accept as a peak.",
                "Reject": "Reject as noise, an error, or a duplicate.",
                "Defer": "Defer for more review.",
            }
            followed = int(decision == mapping.get(str(recommendation)))
        elapsed = max(0.0, time.time() - float(st.session_state[f"trial_start_{trial_id}"]))
        store.save_trial_response(
            {
                "session_id": session_id,
                "trial_id": trial_id,
                "case_id": str(safe["case_id"]),
                "condition": condition,
                "decision_code": DECISION_OPTIONS[decision],
                "decision_label": decision,
                "confidence": confidence,
                "selected_evidence": [primary_evidence],
                "primary_evidence": primary_evidence,
                "optional_explanation": "",
                "explanation_reason": explanation_reason,
                "clarity": clarity,
                "difficulty": None,
                "evidence_disagreement": evidence_disagreement,
                "disagreement_sources": disagreement_sources,
                "recommendation": recommendation,
                "recommendation_followed": followed,
                "response_time_seconds": elapsed,
                "opened_sections": [name for name, value in opened.items() if value],
                "interaction": opened,
            }
        )
        store.log_event(session_id, "trial_submitted", {"decision": decision, "confidence": confidence}, trial_id)
        st.session_state.pop(f"trial_start_{trial_id}", None)
        store.update_progress(session_id, "trials", int(safe["trial_position"]) + 1)
        st.rerun()

    st.caption(
        "The study comparison answer is hidden while you review the same signal in later views. "
        "After all nine decisions, the final page shows the comparison answer and your three decisions for each case."
    )


def render_post_condition(session_id: str, condition: str, store: StudyStore) -> None:
    """Collect short usability and reliance ratings after one condition block is complete."""
    label = FINAL_CONDITION_LABELS.get(condition, condition)
    section = f"post_{condition}"
    st.header(f"Quick check after {label}")
    render_key_terms()
    st.caption("1 = strongly disagree; 5 = strongly agree.")
    with st.form(f"post_condition_{condition}"):
        ratings = {
            code: st.slider(prompt, 1, 5, 3, key=f"post_{condition}_{code}")
            for code, prompt in POST_CONDITION_ITEMS
        }
        extra: dict[str, Any] = {}
        if condition != CONDITION_BASELINE:
            extra["most_useful"] = st.selectbox(
                "Which clue was most useful?",
                PEAKABOO_EVIDENCE_OPTIONS[:-1],
            )
            extra["confusing"] = st.selectbox(
                "Which clue was hardest to understand?",
                ["None"] + PEAKABOO_EVIDENCE_OPTIONS[:-1],
                help="Choose one item. The ? glossary above explains each evidence type.",
            )
            extra["information_amount"] = st.radio(
                "How was the amount of information?",
                ["Too little", "About right", "Too much"],
                horizontal=True,
            )
        if condition == CONDITION_RECOMMENDATION:
            extra["recommendation_influence"] = st.slider(
                "How much did the AI statement “this is a peak” influence your answers (?)?",
                1,
                5,
                3,
                help="1 = not at all; 5 = very strongly. " + TERM_HELP["ai_peak_mark"],
            )
        submitted = st.form_submit_button("Save and continue", type="primary")
    if submitted:
        for code, value in ratings.items():
            _save_single(store, session_id, section, code, value)
        for code, value in extra.items():
            _save_single(store, session_id, section, code, value)
        _save_single(store, session_id, section, "completed", "yes")
        st.rerun()


def render_final(session_id: str, enabled_conditions: list[str], store: StudyStore) -> None:
    """Collect final cross-condition judgments and close the participant session."""
    st.header("Final questions")
    render_key_terms()
    comparison_options = [FINAL_CONDITION_LABELS[item] for item in enabled_conditions] + ["No clear difference"]
    with st.form("final_form"):
        better = st.radio("Which view best supported your decisions?", comparison_options)
        easier = st.radio("Which view was easiest to understand?", comparison_options)
        recommendation_change = st.radio(
            "Did the AI statement “this is a peak” change an answer you would otherwise have given (?)?",
            ["Yes", "No", "Unsure"],
            help=TERM_HELP["ai_peak_mark"],
        )
        numerical_authority = st.slider(
            "The numbers looked more certain than they really were.",
            1,
            5,
            3,
            help="1 = strongly disagree; 5 = strongly agree.",
        )
        routine_use = st.radio(
            "Would you use separate uncertainty clues in your normal review work?",
            ["Yes", "Maybe", "No"],
        )
        comments = st.text_area(
            "Optional: What is the single most important change you would make?",
            max_chars=400,
        )
        submitted = st.form_submit_button("Complete study", type="primary")
    if submitted:
        values = {
            "best_supported_decisions": better,
            "easiest_condition": easier,
            "recommendation_changed_decision": recommendation_change,
            "numerical_authority": numerical_authority,
            "routine_use": routine_use,
            "most_important_change": comments.strip(),
        }
        for code, value in values.items():
            _save_single(store, session_id, "final", code, value)
        _save_single(store, session_id, "final", "completed", "yes")
        store.complete_session(session_id)
        st.rerun()


def render_debrief_answers(session_id: str, assignment: pd.DataFrame, store: StudyStore) -> None:
    """Show comparison answers only after all nine decisions are complete."""
    st.subheader("Answer review")
    st.caption(
        "These are study comparison labels, not perfect chemical truth. They were hidden until the end so they would not affect later views of the same signal."
    )
    responses = store.table("trial_responses")
    responses = responses[responses["session_id"].astype(str) == str(session_id)].copy()
    records: list[dict[str, Any]] = []
    condition_names = {
        CONDITION_BASELINE: "Signal only",
        CONDITION_EVIDENCE: "Separate evidence",
        CONDITION_RECOMMENDATION: "AI says peak",
    }
    for slot, group in assignment.groupby("case_slot", sort=True):
        first = group.iloc[0]
        reference = "Peak" if str(first.get("hidden_reference_status", "")).lower() == "supported" else "Not supported as a peak"
        item: dict[str, Any] = {"Case": int(slot), "Study comparison answer": reference}
        for condition, label in condition_names.items():
            trial_ids = group.loc[group["condition"].astype(str) == condition, "trial_id"].astype(str)
            match = responses[responses["trial_id"].astype(str).isin(trial_ids)]
            item[label] = str(match.iloc[0]["decision_label"]) if not match.empty else "No answer"
        records.append(item)
    with st.popover("? Study comparison answer"):
        st.write(TERM_HELP["reference"])
    st.dataframe(pd.DataFrame(records), use_container_width=True, hide_index=True)


def render_participant_study(config: dict[str, Any], paths: Paths, bank: pd.DataFrame, store: StudyStore) -> None:
    """Route a participant through entry, surveys, practice, trials, block checks, and debrief."""
    if "session_id" not in st.session_state:
        render_entry(config, bank, store)
        return

    session_id = str(st.session_state["session_id"])
    assignment = store.assignment_for_session(session_id)
    if assignment.empty:
        participant_id = str(st.session_state.get("participant_id", ""))
        _, assignment = _initialize_participant(participant_id, config, bank, store)
    response_map = store.survey_response_map(session_id)

    if not _section_complete(response_map, "background", "completed"):
        render_background(session_id, store)
        return
    if not _section_complete(response_map, "current_practice", "completed"):
        render_current_practice(session_id, store)
        return
    if not _section_complete(response_map, "comprehension", "completed"):
        render_tutorial(session_id, store)
        return

    completed = store.completed_trial_ids(session_id)
    condition_sequence = assignment.sort_values("block_number")["condition"].drop_duplicates().tolist()
    for condition in condition_sequence:
        block = assignment.loc[assignment["condition"] == condition]
        block_complete = set(block["trial_id"].astype(str)).issubset(completed)
        if not block_complete:
            explanation_ids = explanation_trial_ids(assignment, int(config["study"].get("explanation_trials", 2)))
            render_trial(session_id, assignment, store, paths, explanation_ids)
            return
        section = f"post_{condition}"
        if not _section_complete(response_map, section, "completed"):
            render_post_condition(session_id, condition, store)
            return

    if not _section_complete(response_map, "final", "completed"):
        render_final(session_id, list(config["study"]["enabled_conditions"]), store)
        return

    st.success("Study complete. Your responses have been saved.")
    render_key_terms(["reference", "peak", "defer", "recommendation"])
    render_debrief_answers(session_id, assignment, store)
    st.write("You may now close this window.")
    if st.button("Return to participant entry"):
        for key in ("session_id", "participant_id", "comprehension_result"):
            st.session_state.pop(key, None)
        st.rerun()
