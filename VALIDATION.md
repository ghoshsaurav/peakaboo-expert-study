# Validation summary

Validated on 2026-08-05.

- 16 automated tests passed.
- Case-bank validation passed.
- Python source compilation passed.
- Demo database contains 12 sessions and 108 decisions.
- Every demo session uses exactly three unique cases repeated across all three conditions.
- All demo sessions use the fixed order: baseline → separate evidence → AI peak mark.
- Every final-condition demo trial records the displayed recommendation as `Accept`.
- Analysis outputs and paper-figure files were regenerated from the v3 demo database.

The Streamlit interface itself must be launched in an environment with the dependencies in `requirements.txt` installed.
