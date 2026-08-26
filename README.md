# Peak-a-boo Expert Study v3.0

A Streamlit study platform for examining how people review difficult chromatographic peak candidates.

## What changed in v3.0

- Fixed study order: **signal only → separate evidence → AI says peak**.
- Exactly **three shared cases** are used in every condition.
- Case 1, Case 2, and Case 3 show the same signal in all three conditions.
- The case selector prioritizes difficult or ambiguous cases rather than obvious peaks.
- In the final condition, the AI message is explicit: **AI DECISION: PEAK — ACCEPT AS A PEAK**.
- Technical terms use plain wording and clickable `?` help throughout participant pages.
- The four practice questions show their answer key at the bottom of the page after submission.
- After all nine decisions, the participant sees the study comparison answer and their three decisions for each case.

## Study conditions

1. **Signal-only view**: the measured signal, smoothed signal, and marked candidate.
2. **Separate-evidence view**: the same signal plus separate clues about noise, repeatability, setting sensitivity, and possible overlap or duplicates.
3. **AI-marks-it-as-a-peak view**: the same signal and evidence plus a clear AI statement that the candidate is a peak and should be accepted.

Each participant makes exactly nine decisions: three cases in each condition.

## Install and run

```bash
python -m pip install -r requirements.txt
streamlit run app.py
```

The default researcher password is `change-me`. Change it in `config/study_config.yaml` or set:

```bash
export PEAKABOO_RESEARCHER_PASSWORD='your-password'
```

## Participant flow

1. Participant ID and consent.
2. Short experience questions.
3. Short questions about current review practice.
4. Four practice questions with a visible answer key after submission.
5. Three signal-only decisions.
6. Three decisions on the same cases with separate evidence.
7. Three decisions on the same cases with separate evidence and the explicit AI peak mark.
8. Short ratings after each condition.
9. Final questions.
10. End-of-study answer review.

The study comparison answer is hidden until all nine decisions are complete. This prevents the answer from influencing the later views of the same signal.

## Candidate decisions

Each trial asks:

- Accept as a peak.
- Reject as noise, an error, or a duplicate.
- Defer for more review.
- Confidence from 0–100.
- The single most influential clue.

A small number of evidence trials include one short explanation question.

## Shared-case design

The assignment algorithm selects three challenging cases and repeats those same three cases in all conditions:

```text
Signal only:       Case 1, Case 2, Case 3
Separate evidence: Case 1, Case 2, Case 3
AI says peak:      Case 1, Case 2, Case 3
```

The order is fixed. Participants may receive different challenging trios, but each participant sees an internally matched set.

This design supports direct within-person comparisons. It also creates a possible learning or memory effect because the signal is repeated. The paper should report that trade-off explicitly.

## Data storage

The active database is:

```text
data/results/study_v3.db
```

Researcher exports include:

- sessions;
- assignments;
- survey responses;
- trial responses;
- analysis-ready trials;
- the SQLite database.

## Case bank

The package contains 48 demonstration cases and self-contained signal windows.

Validate the case bank:

```bash
python scripts/validate_case_bank.py
```

Rebuild from source data:

```bash
python scripts/build_case_bank.py \
  --h5 /path/to/chromatograms.h5 \
  --xlsx /path/to/peak_df.xlsx
```

The assignment code excludes categories beginning with `clear_` and ranks the remaining cases using hidden ambiguity information. The ranking is never shown to participants.

## Demo data

Create a fresh simulated database with 12 demonstration participants:

```bash
python scripts/seed_demo_results.py
```

Copy it into the active database:

```bash
python scripts/load_demo_results.py --yes
```

Reset the active database:

```bash
python scripts/reset_demo.py --yes
```

## Analysis

Generate RQ-aligned tables:

```bash
python analysis/analyze_results.py
```

Generate descriptive paper figures:

```bash
python analysis/generate_paper_figures.py analysis/outputs/analysis_ready_trials.csv
```

Reference annotations are comparison evidence, not perfect chemical truth. Use **reference-aligned** and **reference-discordant** rather than automatically calling decisions correct or incorrect.

## Tests

```bash
pytest
```

Tests cover:

- exactly nine decisions and three per condition;
- fixed condition order;
- the same three cases in all conditions;
- selection of challenging rather than clear cases;
- explicit AI peak recommendation;
- hidden-label removal;
- structured response logging;
- evidence calculations;
- practice-question answer keys and help text.
