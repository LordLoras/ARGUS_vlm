from __future__ import annotations

import sqlite3

# Tables we deliberately omit from the agent's mental model:
#   schema_migrations - Alembic-style metadata, not analytical
#   sqlite_*          - SQLite internal
#   ads_fts*, *_data, *_idx, *_content, *_config - FTS5 shadow tables
#   vec_*             - sqlite-vec virtual tables (vector blobs are not queryable
#                       via sql_readonly; use the vector_similarity tool instead)
_HIDDEN_PREFIXES = ("ads_fts_", "vec_", "sqlite_")
_HIDDEN_EXACT = {"ads_fts", "schema_migrations"}


def _table_columns(conn: sqlite3.Connection, table: str) -> list[tuple[str, str]]:
    rows = conn.execute(f"PRAGMA table_info({table})").fetchall()
    return [(str(r[1]), str(r[2])) for r in rows]


def _list_tables(conn: sqlite3.Connection) -> list[str]:
    rows = conn.execute(
        """
        SELECT name
        FROM sqlite_master
        WHERE type IN ('table', 'view')
          AND name NOT LIKE 'sqlite_%'
        ORDER BY name
        """
    ).fetchall()
    names: list[str] = []
    for row in rows:
        name = str(row[0])
        if name in _HIDDEN_EXACT:
            continue
        if any(name.startswith(prefix) for prefix in _HIDDEN_PREFIXES):
            continue
        names.append(name)
    return names


def render_schema_summary(conn: sqlite3.Connection) -> str:
    """Render a compact schema summary suitable for the agent's system prompt.

    Includes columns + types for every analytical table in the live DB.
    Excludes FTS5 shadow tables and sqlite-vec virtual tables (the agent
    accesses those through dedicated tools, not raw SQL).
    """
    lines: list[str] = []
    for table in _list_tables(conn):
        cols = _table_columns(conn, table)
        if not cols:
            continue
        col_text = ", ".join(f"{name} {dtype.lower() or 'any'}" for name, dtype in cols)
        lines.append(f"- {table}({col_text})")
    if not lines:
        return "(no analytical tables yet)"
    return "\n".join(lines)
