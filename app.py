"""Streamlit entry point for the Peak-a-boo expert study.

The app loads study configuration and case data, opens either the configured
PostgreSQL database or local SQLite database, and routes users to the participant
study or password-protected researcher dashboard.
"""

from __future__ import annotations

import os

import streamlit as st

from src.config import load_config, resolve_paths
from src.data_loader import load_case_bank
from src.logging_store import StudyStore
from src.questionnaires import TERM_HELP, TERM_LABELS
from src.researcher import render_researcher_mode
from src.study import render_participant_study


st.set_page_config(
    page_title="Peak-a-boo Expert Study",
    page_icon="🔬",
    layout="wide",
)

config = load_config()
paths = resolve_paths(config)
bank = load_case_bank(paths.case_bank)

database_url = os.getenv("DATABASE_URL")
store = StudyStore(database_url if database_url else paths.database)

st.sidebar.title("Peak-a-boo study")
mode = st.sidebar.radio(
    "Mode",
    ["Participant study", "Researcher dashboard"],
)

st.sidebar.caption(
    f"Study version: {config['study']['study_version']}"
)
st.sidebar.caption(
    f"Case bank: {config['study']['case_bank_version']}"
)
st.sidebar.caption("9 decisions · 3 shared cases · fixed order")
st.sidebar.markdown(
    "**Order:** signal only → separate evidence → AI says peak"
)

with st.sidebar.expander("Quick word help (?)"):
    for key in [
        "candidate",
        "chromatogram",
        "detectability",
        "perturbation",
        "stability",
        "parameter_robustness",
        "defer",
        "recommendation",
    ]:
        st.markdown(
            f"**? {TERM_LABELS[key]}**  \n{TERM_HELP[key]}"
        )

if mode == "Participant study":
    render_participant_study(config, paths, bank, store)
else:
    render_researcher_mode(config, paths, bank, store)
