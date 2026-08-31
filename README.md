# Peak-a-boo Expert Study

## Status

**In progress.** This repository contains the current expert-study platform for the Peak-a-boo research project. The study software, case-bank workflow, response storage, analysis scripts, and tests are implemented, but the research study and resulting manuscript are still in progress. A final peer-reviewed publication is not yet linked here.

## Introduction

Peak-a-boo studies how people review difficult chromatographic peak candidates when an automated system provides different amounts of information. The study uses the same challenging cases across three fixed conditions: **signal only → separate evidence → AI says peak**. Participants make accept, reject, or defer decisions, report confidence, and identify the evidence that influenced them. The study is designed to measure how decomposed evidence and an explicit AI recommendation affect human review, including appropriate reliance, over-reliance, under-reliance, uncertainty, and decision changes. Reference annotations are used as comparison evidence rather than assumed to be perfect chemical ground truth.

This repository is one part of the broader Peak-a-boo project. The public workbench is maintained at [`washuvis/peak-a-boo`](https://github.com/washuvis/peak-a-boo), while the private internal analytical implementation is maintained at [`washuvis/chromato-peak-app`](https://github.com/washuvis/chromato-peak-app).

## Study Design at a Glance

Each participant sees three shared cases in each of three conditions, for nine decisions total:

```text
Condition 1: Signal only       → Case 1, Case 2, Case 3
Condition 2: Separate evidence → Case 1, Case 2, Case 3
Condition 3: AI says peak      → Case 1, Case 2, Case 3
```

The condition order is fixed. The same three signals are repeated within a participant so decisions can be compared directly across conditions. This design also creates a possible learning or memory effect, which should be reported as a study limitation.

Each trial records:

- accept as a peak, reject, or defer for more review;
- confidence from 0–100;
- the single most influential clue; and
- selected short explanation responses where required.

The final AI condition gives an explicit recommendation that the candidate is a peak and should be accepted. The comparison answer is hidden until all nine decisions are complete so it does not influence later conditions.

## Repository Structure

- `app.py`
  - Main Streamlit entry point.
  - Loads configuration and the case bank, opens the study database, and routes users to participant or researcher mode.

- `src/`
  - Core study package.
  - `config.py`: loads `study_config.yaml` and resolves project paths.
  - `data_loader.py`: loads and validates study cases and signal windows.
  - `assignment.py`: selects challenging cases and creates the repeated within-participant assignment.
  - `evidence.py`: computes and formats evidence shown in the study conditions.
  - `questionnaires.py`: participant questions, response choices, plain-language terms, and help text.
  - `study.py`: participant consent, survey, practice, trial, condition, and completion flow.
  - `researcher.py`: password-protected researcher dashboard and study-management views.
  - `logging_store.py`: SQLite/PostgreSQL storage for sessions, assignments, survey responses, and trial responses.
  - `metrics.py`: study summaries and analysis-ready measures.
  - `visualization.py`: study-specific chromatogram and evidence figures.
  - `models.py`: shared data structures used by the study code.

- `config/`
  - `study_config.yaml`: study version, case-bank version, paths, and study settings.
  - `evidence_definitions.yaml`: definitions used for the evidence shown to participants.
  - `response_codes.yaml`: structured response codes used for logging and analysis.
  - `case_bank_schema.json`: expected fields in the case bank.

- `data/demo/`
  - Demonstration case-bank assets included with the repository.
  - `case_bank.csv`: study case metadata.
  - `signals.npz`: self-contained signal windows used by the cases.
  - `case_bank_summary.json`: summary information about the case bank.

- `data/results/`
  - Local results directory.
  - The repository tracks only `.gitkeep`; participant databases should not be committed.

- `scripts/`
  - `build_case_bank.py`: builds the study case bank from source chromatogram and reference files.
  - `validate_case_bank.py`: checks that the case bank meets the required schema and study rules.
  - `seed_demo_results.py`: creates demonstration participant results.
  - `load_demo_results.py`: copies the demonstration database into the active local database.
  - `reset_demo.py`: resets local demonstration results.
  - `export_anonymized_results.py`: creates an anonymized export for analysis or sharing.

- `analysis/`
  - `analyze_results.py`: generates research-question-aligned analysis tables from study results.
  - `generate_paper_figures.py`: generates descriptive figures for the paper.
  - `data_dictionary.csv`: describes fields used in the analysis outputs.
  - `outputs/`: generated analysis tables and model summaries from demonstration or analysis runs.
  - `paper_figures/`: generated PDF/SVG paper figures.

- `tests/`
  - Tests for assignment logic, evidence calculations, structured logging, privacy behavior, questionnaires, and same-case analysis.

- `STUDY_DESIGN.md`
  - Study-design decisions and rationale.

- `SURVEY_QUESTION_MAP.md`
  - Maps study questions to research goals and expected measures.

- `CASE_BANK_NOTES.md`
  - Notes about case-bank construction and interpretation.

- `PAPER_FIGURE_PLAN.md`
  - Planned result figures and their intended analytical role.

- `VALIDATION.md`
  - Records validation checks completed for the study package.

- `CHANGELOG.md`
  - Records major changes across study versions.

- `requirements.txt`
  - Python dependencies and supported version ranges.

## Getting Started

### Prerequisites and Needed Materials

You need:

- Python 3
- `pip`
- Git
- a terminal or command prompt

This repository does not currently pin one specific Python interpreter version. Supported package ranges are listed in `requirements.txt`:

```text
streamlit>=1.42,<2
plotly>=5.24,<7
pandas>=2.1,<3
numpy>=1.26,<3
scipy>=1.11,<2
PyYAML>=6,<7
h5py>=3.10,<4
openpyxl>=3.1,<4
statsmodels>=0.14,<1
matplotlib>=3.8,<4
pytest>=8,<10
SQLAlchemy>=2.0,<3
psycopg[binary]>=3.2,<4
```

The repository already contains a demonstration case bank under `data/demo/`. Building a new case bank from source research data requires access to the appropriate chromatogram HDF5 file and reference workbook.

### Installation

Clone the repository:

```bash
git clone https://github.com/ghoshsaurav/peakaboo-expert-study.git
cd peakaboo-expert-study
```

Create a virtual environment.

macOS or Linux:

```bash
python -m venv .venv
source .venv/bin/activate
```

Windows PowerShell:

```powershell
python -m venv .venv
.\.venv\Scripts\Activate.ps1
```

Install the required packages:

```bash
python -m pip install -r requirements.txt
```

### Run the Study Application

Start the Streamlit application:

```bash
streamlit run app.py
```

The sidebar provides two modes:

- **Participant study**: runs consent, background questions, practice, the nine review decisions, condition ratings, final questions, and end-of-study review.
- **Researcher dashboard**: provides researcher-only study-management and export views.

The default researcher password is configured in `config/study_config.yaml`. For a deployed study, set a private environment variable instead of relying on the default value:

```bash
export PEAKABOO_RESEARCHER_PASSWORD='your-password'
```

Do not commit real deployment passwords to GitHub.

### Database Storage

The application uses `DATABASE_URL` when that environment variable is set. This supports a PostgreSQL deployment such as Neon. If `DATABASE_URL` is not set, the application uses the local database path defined in `config/study_config.yaml`.

Participant result databases must not be committed to this public repository. The tracked `data/results/` directory contains only `.gitkeep`.

### Validate the Case Bank

Run:

```bash
python scripts/validate_case_bank.py
```

The bundled package contains 48 demonstration cases and self-contained signal windows. The assignment logic excludes categories beginning with `clear_` and prioritizes difficult cases using information that is not shown to participants.

### Rebuild the Case Bank

When approved source research data are available:

```bash
python scripts/build_case_bank.py \
  --h5 /path/to/chromatograms.h5 \
  --xlsx /path/to/peak_df.xlsx
```

Do not commit private source chromatograms or reference workbooks to this public repository.

### Create Demonstration Results

Create a fresh demonstration database with 12 simulated participants:

```bash
python scripts/seed_demo_results.py
```

Load the demonstration database as the active local database:

```bash
python scripts/load_demo_results.py --yes
```

Reset the active demonstration database:

```bash
python scripts/reset_demo.py --yes
```

These scripts are for software testing and figure development. Demonstration results are not human-subject study findings.

### Export Anonymized Results

Use:

```bash
python scripts/export_anonymized_results.py
```

Review the exported fields before sharing any result file. Follow the approved study and data-management procedures for real participant data.

### Run the Analysis

Generate research-question-aligned tables:

```bash
python analysis/analyze_results.py
```

Generate descriptive paper figures:

```bash
python analysis/generate_paper_figures.py analysis/outputs/analysis_ready_trials.csv
```

### Run the Tests

Run:

```bash
pytest
```

The tests cover the repeated-case assignment, fixed condition order, difficult-case selection, evidence calculations, explicit AI recommendation, structured response logging, privacy behavior, questionnaires, and same-case analysis.

## Related Repositories

- [`washuvis/peak-a-boo`](https://github.com/washuvis/peak-a-boo)
  - Public synthetic Peak-a-boo workbench for inspecting uncertain peak detections and review evidence.

- [`washuvis/chromato-peak-app`](https://github.com/washuvis/chromato-peak-app)
  - Private internal analytical implementation containing research data, classical/ML peak-detection code, and the analysis dashboard.

- [`ghoshsaurav/peakaboo-expert-study`](https://github.com/ghoshsaurav/peakaboo-expert-study)
  - This repository; the expert-study application and analysis workflow.

- [`ghoshsaurav/peak-detection`](https://github.com/ghoshsaurav/peak-detection)
  - Earlier exploratory peak-detection prototype that predates the current Peak-a-boo package structure.

## Main Technical Libraries

- [Streamlit](https://streamlit.io/) for the participant and researcher interfaces.
- [Plotly](https://plotly.com/python/) and [Matplotlib](https://matplotlib.org/) for study and paper figures.
- [pandas](https://pandas.pydata.org/) and [NumPy](https://numpy.org/) for data processing.
- [SciPy](https://scipy.org/) for numerical and signal-processing operations used in case/evidence preparation.
- [SQLAlchemy](https://www.sqlalchemy.org/) for database access.
- [PostgreSQL/psycopg](https://www.psycopg.org/) for hosted result storage when `DATABASE_URL` is configured.
- [statsmodels](https://www.statsmodels.org/) for statistical analysis.

## Data and Privacy Notes

The files under `data/demo/` are demonstration study assets. Real participant responses must not be committed to this repository. Keep researcher passwords, database credentials, and deployment secrets in environment variables or the deployment platform's secret manager.

The case bank may be rebuilt from research chromatograms when the project team has approved access to those files. Source research data should remain in their approved private location rather than being copied into this public study repository.

Reference annotations are comparison evidence. Analysis and reporting should use terms such as **reference-aligned** and **reference-discordant** when that distinction is more accurate than calling a participant decision simply correct or incorrect.

## Future Work

Useful next steps include:

- complete expert data collection and evaluate how decisions change across the three information conditions;
- test whether separate evidence improves review decisions or creates additional confusion;
- measure when an explicit AI recommendation produces appropriate reliance, over-reliance, or under-reliance;
- examine whether evidence disagreement is especially useful for identifying cases that need human oversight;
- evaluate differences by participant expertise when the sample supports that analysis;
- refine case selection and study wording based on pilot feedback without exposing hidden comparison labels to participants;
- maintain a clear separation between demonstration results and real participant data; and
- keep study measures and analysis scripts synchronized with the paper's research questions.

## Maintenance Notes

Before changing the study design, review `STUDY_DESIGN.md`, `SURVEY_QUESTION_MAP.md`, and the relevant tests. Changes to condition order, repeated-case logic, AI recommendation wording, response fields, or case-selection rules can change the meaning of the study and should be documented in `CHANGELOG.md`.

When the result schema changes, update `analysis/data_dictionary.csv`, the analysis scripts, and the database/export code together. Run `pytest` and `python scripts/validate_case_bank.py` before using a changed version for data collection.
