from __future__ import annotations

import json
import sqlite3
import uuid
from contextlib import contextmanager
from datetime import datetime, timezone
from pathlib import Path
from typing import Any, Iterator

import pandas as pd


def utc_now() -> str:
    return datetime.now(timezone.utc).isoformat()


class StudyStore:
    def __init__(self, database_path: str | Path):
        self.database_path = Path(database_path)
        self.database_path.parent.mkdir(parents=True, exist_ok=True)
        self.initialize()

    @contextmanager
    def connection(self) -> Iterator[sqlite3.Connection]:
        connection = sqlite3.connect(self.database_path)
        connection.row_factory = sqlite3.Row
        try:
            yield connection
            connection.commit()
        finally:
            connection.close()

    def initialize(self) -> None:
        with self.connection() as connection:
            connection.executescript(
                """
                PRAGMA journal_mode=WAL;
                CREATE TABLE IF NOT EXISTS sessions (
                    session_id TEXT PRIMARY KEY,
                    participant_id TEXT NOT NULL,
                    condition_order TEXT NOT NULL,
                    case_bank_version TEXT NOT NULL,
                    study_version TEXT NOT NULL,
                    started_at TEXT NOT NULL,
                    completed_at TEXT,
                    current_phase TEXT NOT NULL DEFAULT 'background',
                    current_trial_position INTEGER NOT NULL DEFAULT 1,
                    status TEXT NOT NULL DEFAULT 'active'
                );

                CREATE TABLE IF NOT EXISTS assignments (
                    session_id TEXT NOT NULL,
                    trial_id TEXT NOT NULL,
                    case_id TEXT NOT NULL,
                    pair_id TEXT,
                    condition TEXT NOT NULL,
                    block_number INTEGER NOT NULL,
                    trial_position INTEGER NOT NULL,
                    source_type TEXT,
                    hidden_case_category TEXT,
                    hidden_disagreement_type TEXT,
                    hidden_reference_status TEXT,
                    assignment_json TEXT NOT NULL,
                    PRIMARY KEY (session_id, trial_id)
                );

                CREATE TABLE IF NOT EXISTS survey_responses (
                    id INTEGER PRIMARY KEY AUTOINCREMENT,
                    session_id TEXT NOT NULL,
                    section TEXT NOT NULL,
                    question_code TEXT NOT NULL,
                    response_code TEXT,
                    response_label TEXT,
                    response_json TEXT,
                    created_at TEXT NOT NULL,
                    UNIQUE(session_id, section, question_code)
                );

                CREATE TABLE IF NOT EXISTS trial_responses (
                    session_id TEXT NOT NULL,
                    trial_id TEXT NOT NULL,
                    case_id TEXT NOT NULL,
                    condition TEXT NOT NULL,
                    decision_code INTEGER NOT NULL,
                    decision_label TEXT NOT NULL,
                    confidence INTEGER NOT NULL,
                    selected_evidence_json TEXT NOT NULL,
                    primary_evidence TEXT,
                    optional_explanation TEXT,
                    explanation_reason_json TEXT,
                    clarity INTEGER,
                    difficulty INTEGER,
                    evidence_disagreement TEXT,
                    disagreement_sources_json TEXT,
                    recommendation TEXT,
                    recommendation_followed INTEGER,
                    response_time_seconds REAL,
                    opened_sections_json TEXT,
                    interaction_json TEXT,
                    submitted_at TEXT NOT NULL,
                    PRIMARY KEY (session_id, trial_id)
                );

                CREATE TABLE IF NOT EXISTS interaction_events (
                    id INTEGER PRIMARY KEY AUTOINCREMENT,
                    session_id TEXT NOT NULL,
                    trial_id TEXT,
                    event_type TEXT NOT NULL,
                    event_value TEXT,
                    event_time TEXT NOT NULL
                );
                """
            )
            columns = {row[1] for row in connection.execute("PRAGMA table_info(trial_responses)").fetchall()}
            if "primary_evidence" not in columns:
                connection.execute("ALTER TABLE trial_responses ADD COLUMN primary_evidence TEXT")

    def get_or_create_session(
        self,
        participant_id: str,
        condition_order: str,
        case_bank_version: str,
        study_version: str,
    ) -> str:
        participant_id = participant_id.strip()
        if not participant_id:
            raise ValueError("participant_id is required")
        with self.connection() as connection:
            row = connection.execute(
                "SELECT session_id FROM sessions WHERE participant_id = ? AND status = 'active' ORDER BY started_at DESC LIMIT 1",
                (participant_id,),
            ).fetchone()
            if row:
                return str(row["session_id"])
            session_id = str(uuid.uuid4())
            connection.execute(
                """INSERT INTO sessions
                (session_id, participant_id, condition_order, case_bank_version, study_version, started_at)
                VALUES (?, ?, ?, ?, ?, ?)""",
                (session_id, participant_id, condition_order, case_bank_version, study_version, utc_now()),
            )
            return session_id

    def save_assignments(self, session_id: str, assignment: pd.DataFrame) -> None:
        with self.connection() as connection:
            for _, row in assignment.iterrows():
                payload = row.to_dict()
                connection.execute(
                    """INSERT OR IGNORE INTO assignments
                    (session_id, trial_id, case_id, pair_id, condition, block_number, trial_position,
                     source_type, hidden_case_category, hidden_disagreement_type, hidden_reference_status, assignment_json)
                    VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)""",
                    (
                        session_id,
                        str(row["trial_id"]),
                        str(row["case_id"]),
                        str(row.get("pair_id", "")),
                        str(row["condition"]),
                        int(row["block_number"]),
                        int(row["trial_position"]),
                        str(row.get("source_type", "")),
                        str(row.get("hidden_case_category", "")),
                        str(row.get("hidden_disagreement_type", "")),
                        str(row.get("hidden_reference_status", "")),
                        json.dumps(payload, default=str, sort_keys=True),
                    ),
                )

    def assignment_for_session(self, session_id: str) -> pd.DataFrame:
        with self.connection() as connection:
            frame = pd.read_sql_query(
                "SELECT assignment_json FROM assignments WHERE session_id = ? ORDER BY trial_position",
                connection,
                params=(session_id,),
            )
        if frame.empty:
            return pd.DataFrame()
        return pd.DataFrame([json.loads(value) for value in frame["assignment_json"]])

    def save_survey_response(
        self,
        session_id: str,
        section: str,
        question_code: str,
        response_code: Any,
        response_label: Any,
        response: Any = None,
    ) -> None:
        with self.connection() as connection:
            connection.execute(
                """INSERT INTO survey_responses
                (session_id, section, question_code, response_code, response_label, response_json, created_at)
                VALUES (?, ?, ?, ?, ?, ?, ?)
                ON CONFLICT(session_id, section, question_code) DO UPDATE SET
                    response_code=excluded.response_code,
                    response_label=excluded.response_label,
                    response_json=excluded.response_json,
                    created_at=excluded.created_at""",
                (
                    session_id,
                    section,
                    question_code,
                    None if response_code is None else str(response_code),
                    None if response_label is None else str(response_label),
                    json.dumps(response if response is not None else response_label, default=str),
                    utc_now(),
                ),
            )

    def save_trial_response(self, payload: dict[str, Any]) -> None:
        required = {"session_id", "trial_id", "case_id", "condition", "decision_code", "decision_label", "confidence"}
        missing = required - set(payload)
        if missing:
            raise ValueError(f"Missing trial response fields: {sorted(missing)}")
        with self.connection() as connection:
            connection.execute(
                """INSERT OR REPLACE INTO trial_responses
                (session_id, trial_id, case_id, condition, decision_code, decision_label, confidence,
                 selected_evidence_json, primary_evidence, optional_explanation, explanation_reason_json, clarity, difficulty,
                 evidence_disagreement, disagreement_sources_json, recommendation, recommendation_followed,
                 response_time_seconds, opened_sections_json, interaction_json, submitted_at)
                VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)""",
                (
                    payload["session_id"],
                    payload["trial_id"],
                    payload["case_id"],
                    payload["condition"],
                    int(payload["decision_code"]),
                    payload["decision_label"],
                    int(payload["confidence"]),
                    json.dumps(payload.get("selected_evidence", [])),
                    payload.get("primary_evidence"),
                    payload.get("optional_explanation"),
                    json.dumps(payload.get("explanation_reason", [])),
                    payload.get("clarity"),
                    payload.get("difficulty"),
                    payload.get("evidence_disagreement"),
                    json.dumps(payload.get("disagreement_sources", [])),
                    payload.get("recommendation"),
                    payload.get("recommendation_followed"),
                    payload.get("response_time_seconds"),
                    json.dumps(payload.get("opened_sections", [])),
                    json.dumps(payload.get("interaction", {}), default=str),
                    utc_now(),
                ),
            )

    def completed_trial_ids(self, session_id: str) -> set[str]:
        with self.connection() as connection:
            rows = connection.execute(
                "SELECT trial_id FROM trial_responses WHERE session_id = ?", (session_id,)
            ).fetchall()
        return {str(row["trial_id"]) for row in rows}

    def update_progress(self, session_id: str, phase: str, trial_position: int | None = None) -> None:
        with self.connection() as connection:
            if trial_position is None:
                connection.execute(
                    "UPDATE sessions SET current_phase = ? WHERE session_id = ?", (phase, session_id)
                )
            else:
                connection.execute(
                    "UPDATE sessions SET current_phase = ?, current_trial_position = ? WHERE session_id = ?",
                    (phase, int(trial_position), session_id),
                )

    def complete_session(self, session_id: str) -> None:
        with self.connection() as connection:
            connection.execute(
                "UPDATE sessions SET status = 'complete', completed_at = ?, current_phase = 'complete' WHERE session_id = ?",
                (utc_now(), session_id),
            )

    def log_event(self, session_id: str, event_type: str, event_value: Any = None, trial_id: str | None = None) -> None:
        with self.connection() as connection:
            connection.execute(
                "INSERT INTO interaction_events (session_id, trial_id, event_type, event_value, event_time) VALUES (?, ?, ?, ?, ?)",
                (session_id, trial_id, event_type, json.dumps(event_value, default=str), utc_now()),
            )

    def table(self, name: str) -> pd.DataFrame:
        allowed = {"sessions", "assignments", "survey_responses", "trial_responses", "interaction_events"}
        if name not in allowed:
            raise ValueError(f"Unknown table: {name}")
        with self.connection() as connection:
            return pd.read_sql_query(f"SELECT * FROM {name}", connection)

    def survey_response_map(self, session_id: str) -> dict[tuple[str, str], dict[str, Any]]:
        with self.connection() as connection:
            rows = connection.execute(
                "SELECT section, question_code, response_code, response_label, response_json FROM survey_responses WHERE session_id = ?",
                (session_id,),
            ).fetchall()
        return {
            (str(row["section"]), str(row["question_code"])): {
                "response_code": row["response_code"],
                "response_label": row["response_label"],
                "response_json": row["response_json"],
            }
            for row in rows
        }

    def session_record(self, session_id: str) -> dict[str, Any] | None:
        with self.connection() as connection:
            row = connection.execute("SELECT * FROM sessions WHERE session_id = ?", (session_id,)).fetchone()
        return dict(row) if row else None
