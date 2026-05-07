from __future__ import annotations

import sqlite3

from ad_classifier.db.repositories.base import db_value, row_to_dict
from ad_classifier.models.agent import AgentMessageRecord, AgentSessionRecord


class AgentSessionRepository:
    def __init__(self, conn: sqlite3.Connection) -> None:
        self.conn = conn

    def create(self, session: AgentSessionRecord) -> None:
        self.conn.execute(
            """
            INSERT INTO agent_sessions (id, created_at, user_label, context_json)
            VALUES (?, ?, ?, ?)
            """,
            (
                session.id,
                db_value(session.created_at),
                session.user_label,
                session.context_json,
            ),
        )

    def get(self, session_id: str) -> AgentSessionRecord | None:
        row = self.conn.execute(
            "SELECT * FROM agent_sessions WHERE id = ?", (session_id,)
        ).fetchone()
        data = row_to_dict(row)
        return AgentSessionRecord.model_validate(data) if data is not None else None

    def list(self, *, limit: int = 50, offset: int = 0) -> list[AgentSessionRecord]:
        rows = self.conn.execute(
            """
            SELECT *
            FROM agent_sessions
            ORDER BY created_at DESC, id
            LIMIT ? OFFSET ?
            """,
            (limit, offset),
        ).fetchall()
        return [AgentSessionRecord.model_validate(row_to_dict(row)) for row in rows]

    def delete(self, session_id: str) -> None:
        self.conn.execute("DELETE FROM agent_sessions WHERE id = ?", (session_id,))


class AgentMessageRepository:
    def __init__(self, conn: sqlite3.Connection) -> None:
        self.conn = conn

    def append(self, message: AgentMessageRecord) -> int:
        cursor = self.conn.execute(
            """
            INSERT INTO agent_messages (
              session_id, role, content, tool_name, tool_args_json,
              tool_result_json, tokens_in, tokens_out, created_at
            ) VALUES (?,?,?,?,?,?,?,?,?)
            """,
            (
                message.session_id,
                message.role,
                message.content,
                message.tool_name,
                message.tool_args_json,
                message.tool_result_json,
                message.tokens_in,
                message.tokens_out,
                db_value(message.created_at),
            ),
        )
        return int(cursor.lastrowid or 0)

    def list_for_session(self, session_id: str) -> list[AgentMessageRecord]:
        rows = self.conn.execute(
            """
            SELECT *
            FROM agent_messages
            WHERE session_id = ?
            ORDER BY id
            """,
            (session_id,),
        ).fetchall()
        return [AgentMessageRecord.model_validate(row_to_dict(row)) for row in rows]
