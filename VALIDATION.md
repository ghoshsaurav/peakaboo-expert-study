# Validation Summary

Validated on 2026-09-01 using GitHub Actions on Python 3.11 after the final repository-transfer and README cleanup.

- **16 automated tests passed** with `pytest -q`.
- Case-bank validation passed with `python scripts/validate_case_bank.py`.
- Python compilation passed for `src/`, `analysis/`, `scripts/`, `tests/`, and `app.py`.
- The final `analysis/` audit covered `analyze_results.py`, `generate_paper_figures.py`, `data_dictionary.csv`, and `qualitative_codebook.csv`.
- The analysis scripts document their statistical and visualization assumptions and guard paper-figure generation when required columns are unavailable.
- Demo database records contain 12 sessions and 108 decisions.
- Every demo session uses exactly three unique cases repeated across all three conditions.
- All demo sessions use the fixed order: baseline → separate evidence → AI peak mark.
- Every final-condition demo trial records the displayed recommendation as `Accept`.
- The README now uses the current `washuvis` repository locations and follows the VIBE Lab documentation headings for repository structure, prerequisites, installation, and usage.

Continuous validation is defined in `.github/workflows/tests.yml` and runs on pushes and pull requests.

The study reference is treated as comparison evidence rather than perfect chemical truth. The Streamlit interface should still be manually inspected before participant deployment because automated tests do not replace visual and interaction review.
