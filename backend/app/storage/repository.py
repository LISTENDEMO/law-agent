from __future__ import annotations

import json
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
            message_columns = {
                row[1] for row in connection.execute("PRAGMA table_info(messages)").fetchall()
            }
            if "structured_answer_json" not in message_columns:
                connection.execute("ALTER TABLE messages ADD COLUMN structured_answer_json TEXT")

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
            structured_answer_json = (
                result.structured_answer.model_dump_json()
                if result.structured_answer is not None
                else None
            )
            connection.execute(
                """
                INSERT INTO messages (session_id, role, content, structured_answer_json)
                VALUES (?, 'assistant', ?, ?)
                """,
                (session_id, visible_answer, structured_answer_json),
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

    def get_session(self, session_id: str) -> list[dict[str, object]]:
        with self._connect() as connection:
            rows = connection.execute(
                """
                SELECT role, content, created_at, structured_answer_json
                FROM messages
                WHERE session_id = ?
                ORDER BY id
                """,
                (session_id,),
            ).fetchall()
        messages: list[dict[str, object]] = []
        for row in rows:
            message: dict[str, object] = {
                "role": row["role"],
                "content": row["content"],
                "created_at": row["created_at"],
                "structured_answer": (
                    json.loads(row["structured_answer_json"])
                    if row["structured_answer_json"]
                    else None
                ),
            }
            messages.append(message)
        return messages

    def list_sessions(self, *, limit: int = 50) -> list[dict[str, object]]:
        with self._connect() as connection:
            rows = connection.execute(
                """
                SELECT
                    sessions.id,
                    sessions.created_at,
                    COALESCE(MAX(messages.created_at), sessions.created_at) AS updated_at,
                    COALESCE(
                        (
                            SELECT first_user.content
                            FROM messages AS first_user
                            WHERE first_user.session_id = sessions.id
                              AND first_user.role = 'user'
                            ORDER BY first_user.id
                            LIMIT 1
                        ),
                        '新会话'
                    ) AS title,
                    COALESCE(
                        (
                            SELECT last_message.content
                            FROM messages AS last_message
                            WHERE last_message.session_id = sessions.id
                            ORDER BY last_message.id DESC
                            LIMIT 1
                        ),
                        ''
                    ) AS last_message,
                    COUNT(DISTINCT messages.id) AS message_count,
                    COUNT(DISTINCT runs.id) AS run_count,
                    COALESCE(MAX(messages.id), 0) AS last_message_id
                FROM sessions
                LEFT JOIN messages ON messages.session_id = sessions.id
                LEFT JOIN runs ON runs.session_id = sessions.id
                GROUP BY sessions.id
                ORDER BY last_message_id DESC, sessions.created_at DESC
                LIMIT ?
                """,
                (limit,),
            ).fetchall()
        return [dict(row) for row in rows]

    def get_session_runs(self, session_id: str) -> list[dict[str, object]]:
        with self._connect() as connection:
            rows = connection.execute(
                """
                SELECT id, query, result_json, created_at
                FROM runs
                WHERE session_id = ?
                ORDER BY created_at DESC, id DESC
                """,
                (session_id,),
            ).fetchall()
        runs: list[dict[str, object]] = []
        for row in rows:
            result = WorkflowResult.model_validate_json(row["result_json"])
            runs.append(
                {
                    "id": row["id"],
                    "query": row["query"],
                    "status": result.status,
                    "route": result.route,
                    "risk_level": result.risk_level,
                    "created_at": row["created_at"],
                    "agents_executed": result.agents_executed,
                    "evidence_count": len(result.evidence),
                }
            )
        return runs

    def get_latest_run(self, session_id: str) -> dict[str, object] | None:
        with self._connect() as connection:
            row = connection.execute(
                """
                SELECT id, session_id, result_json
                FROM runs
                WHERE session_id = ?
                ORDER BY created_at DESC, id DESC
                LIMIT 1
                """,
                (session_id,),
            ).fetchone()
        if row is None:
            return None
        result = WorkflowResult.model_validate_json(row["result_json"])
        return {
            "run_id": row["id"],
            "session_id": row["session_id"],
            "events_url": f"/api/v1/chat/{row['id']}/events",
            "result": result.model_dump(mode="json"),
        }

    def list_recent_runs(self, *, limit: int = 20) -> list[dict[str, object]]:
        with self._connect() as connection:
            rows = connection.execute(
                """
                SELECT id, session_id, query, result_json, created_at
                FROM runs
                ORDER BY created_at DESC, id DESC
                LIMIT ?
                """,
                (limit,),
            ).fetchall()
        runs: list[dict[str, object]] = []
        for row in rows:
            result = WorkflowResult.model_validate_json(row["result_json"])
            runs.append(
                {
                    "id": row["id"],
                    "session_id": row["session_id"],
                    "query": row["query"],
                    "status": result.status,
                    "route": result.route,
                    "risk_level": result.risk_level,
                    "created_at": row["created_at"],
                    "agents_executed": result.agents_executed,
                    "evidence_count": len(result.evidence),
                }
            )
        return runs

    def get_context(self, session_id: str, *, limit: int = 8) -> list[dict[str, str]]:
        with self._connect() as connection:
            rows = connection.execute(
                """
                SELECT role, content, created_at
                FROM (
                    SELECT id, role, content, created_at
                    FROM messages
                    WHERE session_id = ?
                    ORDER BY id DESC
                    LIMIT ?
                )
                ORDER BY id
                """,
                (session_id, limit),
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
