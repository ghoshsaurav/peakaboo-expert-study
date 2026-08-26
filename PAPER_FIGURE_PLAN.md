# Paper figure and results plan

The scripts generate descriptive figures from the analysis-ready CSV. Inferential claims should be added only after participant- and case-aware analysis.

## Figure 1 — Study concept

**RQ connection:** Overall framing.

**Meaning:** AI produces a candidate; the person receives signal only, decomposed evidence, or the same evidence plus an explicit AI peak mark; the person accepts, rejects, or defers.

**Image-generation prompt:**

> Create a clean CHI-style vector diagram of an AI-assisted candidate-review task. On the left, an AI system surfaces an ambiguous candidate. In the center, show three conditions: signal only; the same case with separate evidence; the same case with separate evidence plus a clear AI statement that it is a peak. Under decomposed evidence, show detectability, stability, parameter robustness, structural ambiguity, and provenance as separate pieces. On the right, show Accept, Reject, and Defer. Use chromatography only as a small example and make the task general enough for medical review, quality control, security alerts, and scientific anomaly detection. White background, restrained academic style, accessible contrast, no decorative robot imagery.

## Figure 2 — Decisions by condition

**RQ connection:** RQ2.

**File:** `figure_decisions_by_condition.pdf`

**Meaning:** Shows whether decomposed evidence or recommendations change Accept, Reject, and Defer rates.

**Supported claim example:** “Decomposed evidence primarily changed deferral rather than acceptance.” Use only when the observed estimates support it.


## Figure 2A — Same-case decision changes

**RQ connection:** RQ2 and RQ4.

**File:** `same_case_decision_changes.csv` can be used to generate this figure.

**Meaning:** For each participant and case, connect the decision across signal only, separate evidence, and AI says peak. Because the exact same signal is repeated, the figure shows where added evidence or AI advice changed judgment.

**Recommended form:** A three-column alluvial or transition plot, supplemented by counts and participant-level uncertainty. Do not use an image generator for the data values.

## Figure 3 — Decision quality, calibration, and deferral

**RQ connection:** RQ2.

**File:** `figure_condition_outcomes.pdf`

**Meaning:** Compares reference alignment, deferral, and calibration error across conditions.

**Supported claim example:** “Evidence improved confidence calibration without increasing overall acceptance.”

## Figure 4 — Evidence use

**RQ connection:** RQ2 and RQ3.

**File:** `figure_evidence_usage.pdf`

**Meaning:** Shows which information participants reported as most influential.

**Supported claim example:** “Participants used stability less often than detectability and signal shape.”

## Figure 5 — Evidence conflict

**RQ connection:** RQ3.

**File:** `figure_evidence_conflict.pdf`

**Meaning:** Compares agreement and conflict cases on deferral, reference alignment, and response time.

**Supported claim example:** “Conflict increased review time and deferral, suggesting that disagreement was noticed but required additional reasoning.”

## Figure 6 — Confidence calibration

**RQ connection:** RQ2.

**File:** `figure_confidence_calibration.pdf`

**Meaning:** Compares reported confidence with observed reference alignment.

**Supported claim example:** “Decomposed evidence reduced high-confidence reference-discordant decisions.”

## Figure 7 — Recommendation reliance

**RQ connection:** RQ4.

**File:** `figure_reliance_categories.pdf`

**Meaning:** Separates appropriate reliance, over-reliance, under-reliance, and appropriate skepticism.

**Supported claim example:** “Participants followed some reference-discordant recommendations, but also contested others.”

## Recommended paper results layout

### 1. Current practice — RQ1

Report participant background, information normally used, deferral reasons, and cost asymmetry.

### 2. Effects of decomposed evidence — RQ2

Report decision distribution, reference alignment, confidence calibration, response time, and deferral.

### 3. Evidence use and conflict — RQ3

Report most influential evidence, conflict recognition, clarity, and behavior in disagreement cases.

### 4. Recommendation reliance — RQ4

Report following or resisting the explicit AI peak mark, plus the four reliance categories.

### 5. General design implications

Discuss candidate-review systems beyond chromatography:

- evidence should be decomposed rather than collapsed into one score;
- disagreement should be visible rather than hidden;
- deferral should be treated as a valid outcome;
- evidence and recommendations should remain separate;
- uncertainty displays must be evaluated for understanding, not only availability.
