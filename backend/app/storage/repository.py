from __future__ import annotations

import sqlite3
import uuid
from pathlib import Path

from app.agents.workflow import AgentEvent, WorkflowResult
from app.domain.models import Evidence


class Repository:
    def __init__(self, path: str | Path) -> None:
        self.path = Path(path)
        self.path.parent.mkdir(parents=True, exist_ok=True)
        self._migrate()

    def _connect(self) -> sqlite3.Connection:
        connection = sqlite3.connect(self.path, timeout=5)
        connection.row_factory = sqlite3.Row
        connection.execute("PRAGMA foreign_keys = ON")
        return connection

    def _migrate(self) -> None:
        with self._connect() as connection:
            connection.executescript(
                """
                CREATE TABLE IF NOT EXISTS sessions (
                    id TEXT PRIMARY KEY,
                    created_at TEXT NOT NULL DEFAULT CURRENT_TIMESTAMP
                );
                CREATE TABLE IF NOT EXISTS runs (
                    id TEXT PRIMARY KEY,
                    session_id TEXT NOT NULL REFERENCES sessions(id) ON DELETE CASCADE,
                    query TEXT NOT NULL,
                    result_json TEXT NOT NULL,
                    created_at TEXT NOT NULL DEFAULT CURRENT_TIMESTAMP
                );
                CREATE TABLE IF NOT EXISTS messages (
                    id INTEGER PRIMARY KEY AUTOINCREMENT,
                    session_id TEXT NOT NULL REFERENCES sessions(id) ON DELETE CASCADE,
                    role TEXT NOT NULL,
                    content TEXT NOT NULL,
                    created_at TEXT NOT NULL DEFAULT CURRENT_TIMESTAMP
                );
                CREATE TABLE IF NOT EXISTS events (
                    run_id TEXT NOT NULL REFERENCES runs(id) ON DELETE CASCADE,
                    sequence INTEGER NOT NULL,
                    event_json TEXT NOT NULL,
                    PRIMARY KEY (run_id, sequence)
                );
                CREATE TABLE IF NOT EXISTS sources (
                    article_id TEXT PRIMARY KEY,
                    source_json TEXT NOT NULL
                );
                """
            )

    def create_session(self) -> str:
        session_id = str(uuid.uuid4())
        with self._connect() as connection:
            connection.execute("INSERT INTO sessions (id) VALUES (?)", (session_id,))
        return session_id

    def save_run(self, session_id: str, query: str, result: WorkflowResult) -> str:
        run_id = str(uuid.uuid4())
        with self._connect() as connection:
            connection.execute(
                "INSERT INTO runs (id, session_id, query, result_json) VALUES (?, ?, ?, ?)",
                (run_id, session_id, query, result.model_dump_json()),
            )
            connection.execute(
                "INSERT INTO messages (session_id, role, content) VALUES (?, 'user', ?)",
                (session_id, query),
            )
            visible_answer = result.answer or result.clarification or ""
            connection.execute(
                "INSERT INTO messages (session_id, role, content) VALUES (?, 'assistant', ?)",
                (session_id, visible_answer),
            )
            connection.executemany(
                "INSERT INTO events (run_id, sequence, event_json) VALUES (?, ?, ?)",
                [
                    (run_id, event.sequence, event.model_dump_json())
                    for event in result.events
                ],
            )
            for evidence in result.evidence:
                connection.execute(
                    "INSERT OR REPLACE INTO sources (article_id, source_json) VALUES (?, ?)",
                    (evidence.article_id, evidence.model_dump_json()),
                )
        return run_id

    def get_events(self, run_id: str) -> list[AgentEvent]:
        with self._connect() as connection:
            rows = connection.execute(
                "SELECT event_json FROM events WHERE run_id = ? ORDER BY sequence", (run_id,)
            ).fetchall()
        return [AgentEvent.model_validate_json(row["event_json"]) for row in rows]

    def get_session(self, session_id: str) -> list[dict[str, str]]:
        with self._connect() as connection:
            rows = connection.execute(
                "SELECT role, content, created_at FROM messages WHERE session_id = ? ORDER BY id",
                (session_id,),
            ).fetchall()
        return [dict(row) for row in rows]

    def get_source(self, article_id: str) -> Evidence | None:
        with self._connect() as connection:
            row = connection.execute(
                "SELECT source_json FROM sources WHERE article_id = ?", (article_id,)
            ).fetchone()
        return Evidence.model_validate_json(row["source_json"]) if row else None

    def delete_session(self, session_id: str) -> bool:
        with self._connect() as connection:
            cursor = connection.execute("DELETE FROM sessions WHERE id = ?", (session_id,))
        return cursor.rowcount > 0
