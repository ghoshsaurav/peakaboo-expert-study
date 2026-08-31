"""Store study sessions, assignments, responses, progress, and interaction events.

The storage layer supports either a local SQLite database or a PostgreSQL
connection supplied through ``DATABASE_URL``. All writes use SQLAlchemy
transactions so the participant and researcher views share one consistent data
model.
"""

from __future__ import annotations

import json
import uuid
from contextlib import contextmanager
from datetime import datetime, timezone
from pathlib import Path
from typing import Any, Iterator

import pandas as pd
from sqlalchemy import create_engine, inspect, text
from sqlalchemy.engine import Connection, Engine


def utc_now() -> str:
    """Return the current UTC time as an ISO-formatted string for study records."""
    return datetime.now(timezone.utc).isoformat()


class StudyStore:
    """Database interface for all persistent expert-study state and responses."""

    def __init__(self, database: str | Path):
        """Open a PostgreSQL/SQLite database and create the required study tables."""
        raw_database = str(database)

        if raw_database.startswith("postgresql://"):
            database_url = raw_database.replace(
                "postgresql://",
                "postgresql+psycopg://",
                1,
            )
        elif raw_database.startswith("postgres://"):
            database_url = raw_database.replace(
                "postgres://",
                "postgresql+psycopg://",
                1,
            )
        elif raw_database.startswith("sqlite://"):
            database_url = raw_database
        else:
            path = Path(raw_database)
            path.parent.mkdir(
                parents=True,
                exist_ok=True,
            )
            database_url = (
                f"sqlite:///{path.resolve().as_posix()}"
            )

        self.engine: Engine = create_engine(
            database_url,
            pool_pre_ping=True,
            pool_recycle=300,
        )

        self.is_postgres = (
            self.engine.dialect.name == "postgresql"
        )
        self.is_sqlite = (
            self.engine.dialect.name == "sqlite"
        )

        self.initialize()

    @contextmanager
    def connection(self) -> Iterator[Connection]:
        """Yield a transaction-scoped database connection that commits on success."""
        with self.engine.begin() as connection:
            yield connection

    def initialize(self) -> None:
        """Create the study schema and apply the small backward-compatible migration."""
        if self.is_postgres:
            id_column = "BIGSERIAL PRIMARY KEY"
            response_time_type = "DOUBLE PRECISION"
        else:
            id_column = (
                "INTEGER PRIMARY KEY AUTOINCREMENT"
            )
            response_time_type = "REAL"

        statements = [
            """
            CREATE TABLE IF NOT EXISTS sessions (
                session_id TEXT PRIMARY KEY,
                participant_id TEXT NOT NULL,
                condition_order TEXT NOT NULL,
                case_bank_version TEXT NOT NULL,
                study_version TEXT NOT NULL,
                started_at TEXT NOT NULL,
                completed_at TEXT,
                current_phase TEXT NOT NULL
                    DEFAULT 'background',
                current_trial_position INTEGER NOT NULL
                    DEFAULT 1,
                status TEXT NOT NULL DEFAULT 'active'
            )
            """,
            """
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
            )
            """,
            f"""
            CREATE TABLE IF NOT EXISTS survey_responses (
                id {id_column},
                session_id TEXT NOT NULL,
                section TEXT NOT NULL,
                question_code TEXT NOT NULL,
                response_code TEXT,
                response_label TEXT,
                response_json TEXT,
                created_at TEXT NOT NULL,
                UNIQUE(
                    session_id,
                    section,
                    question_code
                )
            )
            """,
            f"""
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
                response_time_seconds {response_time_type},
                opened_sections_json TEXT,
                interaction_json TEXT,
                submitted_at TEXT NOT NULL,
                PRIMARY KEY (session_id, trial_id)
            )
            """,
            f"""
            CREATE TABLE IF NOT EXISTS interaction_events (
                id {id_column},
                session_id TEXT NOT NULL,
                trial_id TEXT,
                event_type TEXT NOT NULL,
                event_value TEXT,
                event_time TEXT NOT NULL
            )
            """,
        ]

        with self.connection() as connection:
            for statement in statements:
                connection.execute(text(statement))

        columns = {
            column["name"]
            for column in inspect(
                self.engine
            ).get_columns("trial_responses")
        }

        if "primary_evidence" not in columns:
            with self.connection() as connection:
                connection.execute(
                    text(
                        """
                        ALTER TABLE trial_responses
                        ADD COLUMN primary_evidence TEXT
                        """
                    )
                )

    def get_or_create_session(
        self,
        participant_id: str,
        condition_order: str,
        case_bank_version: str,
        study_version: str,
    ) -> str:
        """Resume the latest active session for a participant or create a new one."""
        participant_id = participant_id.strip()

        if not participant_id:
            raise ValueError(
                "participant_id is required"
            )

        with self.connection() as connection:
            row = connection.execute(
                text(
                    """
                    SELECT session_id
                    FROM sessions
                    WHERE participant_id = :participant_id
                      AND status = 'active'
                    ORDER BY started_at DESC
                    LIMIT 1
                    """
                ),
                {
                    "participant_id": participant_id
                },
            ).mappings().first()

            if row:
                return str(row["session_id"])

            session_id = str(uuid.uuid4())

            connection.execute(
                text(
                    """
                    INSERT INTO sessions
                    (
                        session_id,
                        participant_id,
                        condition_order,
                        case_bank_version,
                        study_version,
                        started_at
                    )
                    VALUES
                    (
                        :session_id,
                        :participant_id,
                        :condition_order,
                        :case_bank_version,
                        :study_version,
                        :started_at
                    )
                    """
                ),
                {
                    "session_id": session_id,
                    "participant_id": participant_id,
                    "condition_order": condition_order,
                    "case_bank_version":
                        case_bank_version,
                    "study_version": study_version,
                    "started_at": utc_now(),
                },
            )

            return session_id

    def save_assignments(
        self,
        session_id: str,
        assignment: pd.DataFrame,
    ) -> None:
        """Persist a participant's deterministic case assignment without duplicating trials."""
        with self.connection() as connection:
            for _, row in assignment.iterrows():
                payload = row.to_dict()

                connection.execute(
                    text(
                        """
                        INSERT INTO assignments
                        (
                            session_id,
                            trial_id,
                            case_id,
                            pair_id,
                            condition,
                            block_number,
                            trial_position,
                            source_type,
                            hidden_case_category,
                            hidden_disagreement_type,
                            hidden_reference_status,
                            assignment_json
                        )
                        VALUES
                        (
                            :session_id,
                            :trial_id,
                            :case_id,
                            :pair_id,
                            :condition,
                            :block_number,
                            :trial_position,
                            :source_type,
                            :hidden_case_category,
                            :hidden_disagreement_type,
                            :hidden_reference_status,
                            :assignment_json
                        )
                        ON CONFLICT
                            (session_id, trial_id)
                        DO NOTHING
                        """
                    ),
                    {
                        "session_id": session_id,
                        "trial_id":
                            str(row["trial_id"]),
                        "case_id":
                            str(row["case_id"]),
                        "pair_id":
                            str(row.get(
                                "pair_id",
                                "",
                            )),
                        "condition":
                            str(row["condition"]),
                        "block_number":
                            int(row["block_number"]),
                        "trial_position":
                            int(row["trial_position"]),
                        "source_type":
                            str(row.get(
                                "source_type",
                                "",
                            )),
                        "hidden_case_category":
                            str(row.get(
                                "hidden_case_category",
                                "",
                            )),
                        "hidden_disagreement_type":
                            str(row.get(
                                "hidden_disagreement_type",
                                "",
                            )),
                        "hidden_reference_status":
                            str(row.get(
                                "hidden_reference_status",
                                "",
                            )),
                        "assignment_json":
                            json.dumps(
                                payload,
                                default=str,
                                sort_keys=True,
                            ),
                    },
                )

    def assignment_for_session(
        self,
        session_id: str,
    ) -> pd.DataFrame:
        """Load the ordered assignment records for a participant session."""
        with self.connection() as connection:
            frame = pd.read_sql_query(
                text(
                    """
                    SELECT assignment_json
                    FROM assignments
                    WHERE session_id = :session_id
                    ORDER BY trial_position
                    """
                ),
                connection,
                params={
                    "session_id": session_id
                },
            )

        if frame.empty:
            return pd.DataFrame()

        return pd.DataFrame(
            [
                json.loads(value)
                for value
                in frame["assignment_json"]
            ]
        )

    def save_survey_response(
        self,
        session_id: str,
        section: str,
        question_code: str,
        response_code: Any,
        response_label: Any,
        response: Any = None,
    ) -> None:
        """Insert or replace one structured questionnaire response for a session."""
        with self.connection() as connection:
            connection.execute(
                text(
                    """
                    INSERT INTO survey_responses
                    (
                        session_id,
                        section,
                        question_code,
                        response_code,
                        response_label,
                        response_json,
                        created_at
                    )
                    VALUES
                    (
                        :session_id,
                        :section,
                        :question_code,
                        :response_code,
                        :response_label,
                        :response_json,
                        :created_at
                    )
                    ON CONFLICT
                    (
                        session_id,
                        section,
                        question_code
                    )
                    DO UPDATE SET
                        response_code =
                            excluded.response_code,
                        response_label =
                            excluded.response_label,
                        response_json =
                            excluded.response_json,
                        created_at =
                            excluded.created_at
                    """
                ),
                {
                    "session_id": session_id,
                    "section": section,
                    "question_code":
                        question_code,
                    "response_code":
                        None
                        if response_code is None
                        else str(response_code),
                    "response_label":
                        None
                        if response_label is None
                        else str(response_label),
                    "response_json":
                        json.dumps(
                            response
                            if response is not None
                            else response_label,
                            default=str,
                        ),
                    "created_at": utc_now(),
                },
            )

    def save_trial_response(
        self,
        payload: dict[str, Any],
    ) -> None:
        """Validate and upsert one participant decision with its evidence and interaction fields."""
        required = {
            "session_id",
            "trial_id",
            "case_id",
            "condition",
            "decision_code",
            "decision_label",
            "confidence",
        }

        missing = required - set(payload)

        if missing:
            raise ValueError(
                "Missing trial response fields: "
                f"{sorted(missing)}"
            )

        with self.connection() as connection:
            connection.execute(
                text(
                    """
                    INSERT INTO trial_responses
                    (
                        session_id,
                        trial_id,
                        case_id,
                        condition,
                        decision_code,
                        decision_label,
                        confidence,
                        selected_evidence_json,
                        primary_evidence,
                        optional_explanation,
                        explanation_reason_json,
                        clarity,
                        difficulty,
                        evidence_disagreement,
                        disagreement_sources_json,
                        recommendation,
                        recommendation_followed,
                        response_time_seconds,
                        opened_sections_json,
                        interaction_json,
                        submitted_at
                    )
                    VALUES
                    (
                        :session_id,
                        :trial_id,
                        :case_id,
                        :condition,
                        :decision_code,
                        :decision_label,
                        :confidence,
                        :selected_evidence_json,
                        :primary_evidence,
                        :optional_explanation,
                        :explanation_reason_json,
                        :clarity,
                        :difficulty,
                        :evidence_disagreement,
                        :disagreement_sources_json,
                        :recommendation,
                        :recommendation_followed,
                        :response_time_seconds,
                        :opened_sections_json,
                        :interaction_json,
                        :submitted_at
                    )
                    ON CONFLICT
                        (session_id, trial_id)
                    DO UPDATE SET
                        case_id =
                            excluded.case_id,
                        condition =
                            excluded.condition,
                        decision_code =
                            excluded.decision_code,
                        decision_label =
                            excluded.decision_label,
                        confidence =
                            excluded.confidence,
                        selected_evidence_json =
                            excluded.selected_evidence_json,
                        primary_evidence =
                            excluded.primary_evidence,
                        optional_explanation =
                            excluded.optional_explanation,
                        explanation_reason_json =
                            excluded.explanation_reason_json,
                        clarity =
                            excluded.clarity,
                        difficulty =
                            excluded.difficulty,
                        evidence_disagreement =
                            excluded.evidence_disagreement,
                        disagreement_sources_json =
                            excluded.disagreement_sources_json,
                        recommendation =
                            excluded.recommendation,
                        recommendation_followed =
                            excluded.recommendation_followed,
                        response_time_seconds =
                            excluded.response_time_seconds,
                        opened_sections_json =
                            excluded.opened_sections_json,
                        interaction_json =
                            excluded.interaction_json,
                        submitted_at =
                            excluded.submitted_at
                    """
                ),
                {
                    "session_id":
                        payload["session_id"],
                    "trial_id":
                        payload["trial_id"],
                    "case_id":
                        payload["case_id"],
                    "condition":
                        payload["condition"],
                    "decision_code":
                        int(
                            payload[
                                "decision_code"
                            ]
                        ),
                    "decision_label":
                        payload[
                            "decision_label"
                        ],
                    "confidence":
                        int(
                            payload[
                                "confidence"
                            ]
                        ),
                    "selected_evidence_json":
                        json.dumps(
                            payload.get(
                                "selected_evidence",
                                [],
                            )
                        ),
                    "primary_evidence":
                        payload.get(
                            "primary_evidence"
                        ),
                    "optional_explanation":
                        payload.get(
                            "optional_explanation"
                        ),
                    "explanation_reason_json":
                        json.dumps(
                            payload.get(
                                "explanation_reason",
                                [],
                            )
                        ),
                    "clarity":
                        payload.get("clarity"),
                    "difficulty":
                        payload.get("difficulty"),
                    "evidence_disagreement":
                        payload.get(
                            "evidence_disagreement"
                        ),
                    "disagreement_sources_json":
                        json.dumps(
                            payload.get(
                                "disagreement_sources",
                                [],
                            )
                        ),
                    "recommendation":
                        payload.get(
                            "recommendation"
                        ),
                    "recommendation_followed":
                        payload.get(
                            "recommendation_followed"
                        ),
                    "response_time_seconds":
                        payload.get(
                            "response_time_seconds"
                        ),
                    "opened_sections_json":
                        json.dumps(
                            payload.get(
                                "opened_sections",
                                [],
                            )
                        ),
                    "interaction_json":
                        json.dumps(
                            payload.get(
                                "interaction",
                                {},
                            ),
                            default=str,
                        ),
                    "submitted_at":
                        utc_now(),
                },
            )

    def completed_trial_ids(
        self,
        session_id: str,
    ) -> set[str]:
        """Return the trial IDs already submitted for a participant session."""
        with self.connection() as connection:
            rows = connection.execute(
                text(
                    """
                    SELECT trial_id
                    FROM trial_responses
                    WHERE session_id = :session_id
                    """
                ),
                {
                    "session_id": session_id
                },
            ).mappings().all()

        return {
            str(row["trial_id"])
            for row in rows
        }

    def update_progress(
        self,
        session_id: str,
        phase: str,
        trial_position: int | None = None,
    ) -> None:
        """Update the participant's current study phase and optional trial position."""
        with self.connection() as connection:
            if trial_position is None:
                connection.execute(
                    text(
                        """
                        UPDATE sessions
                        SET current_phase = :phase
                        WHERE session_id = :session_id
                        """
                    ),
                    {
                        "phase": phase,
                        "session_id":
                            session_id,
                    },
                )
            else:
                connection.execute(
                    text(
                        """
                        UPDATE sessions
                        SET
                            current_phase = :phase,
                            current_trial_position =
                                :trial_position
                        WHERE session_id = :session_id
                        """
                    ),
                    {
                        "phase": phase,
                        "trial_position":
                            int(trial_position),
                        "session_id":
                            session_id,
                    },
                )

    def complete_session(
        self,
        session_id: str,
    ) -> None:
        """Mark a participant session complete and record its completion time."""
        with self.connection() as connection:
            connection.execute(
                text(
                    """
                    UPDATE sessions
                    SET
                        status = 'complete',
                        completed_at =
                            :completed_at,
                        current_phase = 'complete'
                    WHERE session_id = :session_id
                    """
                ),
                {
                    "completed_at": utc_now(),
                    "session_id": session_id,
                },
            )

    def log_event(
        self,
        session_id: str,
        event_type: str,
        event_value: Any = None,
        trial_id: str | None = None,
    ) -> None:
        """Append a timestamped participant interaction event for optional behavior analysis."""
        with self.connection() as connection:
            connection.execute(
                text(
                    """
                    INSERT INTO interaction_events
                    (
                        session_id,
                        trial_id,
                        event_type,
                        event_value,
                        event_time
                    )
                    VALUES
                    (
                        :session_id,
                        :trial_id,
                        :event_type,
                        :event_value,
                        :event_time
                    )
                    """
                ),
                {
                    "session_id": session_id,
                    "trial_id": trial_id,
                    "event_type": event_type,
                    "event_value":
                        json.dumps(
                            event_value,
                            default=str,
                        ),
                    "event_time": utc_now(),
                },
            )

    def table(
        self,
        name: str,
    ) -> pd.DataFrame:
        """Read one allow-listed study table into a pandas DataFrame."""
        allowed = {
            "sessions",
            "assignments",
            "survey_responses",
            "trial_responses",
            "interaction_events",
        }

        if name not in allowed:
            raise ValueError(
                f"Unknown table: {name}"
            )

        with self.connection() as connection:
            return pd.read_sql_query(
                text(
                    f"SELECT * FROM {name}"
                ),
                connection,
            )

    def survey_response_map(
        self,
        session_id: str,
    ) -> dict[
        tuple[str, str],
        dict[str, Any],
    ]:
        """Return questionnaire responses keyed by ``(section, question_code)``."""
        with self.connection() as connection:
            rows = connection.execute(
                text(
                    """
                    SELECT
                        section,
                        question_code,
                        response_code,
                        response_label,
                        response_json
                    FROM survey_responses
                    WHERE session_id = :session_id
                    """
                ),
                {
                    "session_id": session_id
                },
            ).mappings().all()

        return {
            (
                str(row["section"]),
                str(row["question_code"]),
            ): {
                "response_code":
                    row["response_code"],
                "response_label":
                    row["response_label"],
                "response_json":
                    row["response_json"],
            }
            for row in rows
        }

    def session_record(
        self,
        session_id: str,
    ) -> dict[str, Any] | None:
        """Return one session row as a dictionary, or ``None`` if it does not exist."""
        with self.connection() as connection:
            row = connection.execute(
                text(
                    """
                    SELECT *
                    FROM sessions
                    WHERE session_id = :session_id
                    """
                ),
                {
                    "session_id": session_id
                },
            ).mappings().first()

        return dict(row) if row else None
