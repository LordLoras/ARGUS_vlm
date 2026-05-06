from __future__ import annotations

import sqlite3
from contextlib import suppress
from dataclasses import dataclass
from pathlib import Path
from urllib.parse import quote

MIGRATIONS_DIR = Path(__file__).with_name("migrations")


class SqliteVecUnavailableError(RuntimeError):
    pass


@dataclass(frozen=True)
class DatabaseInitResult:
    db_path: Path
    journal_mode: str
    sqlite_vec_version: str | None
    migrations_applied: list[str]


def _sqlite_uri(path: Path, mode: str) -> str:
    quoted_path = quote(path.expanduser().resolve().as_posix(), safe="/:")
    return f"file:{quoted_path}?mode={mode}"


def open_database(path: Path, *, readonly: bool = False) -> sqlite3.Connection:
    db_path = path.expanduser().resolve()
    if not readonly:
        db_path.parent.mkdir(parents=True, exist_ok=True)
        conn = sqlite3.connect(db_path)
    else:
        conn = sqlite3.connect(_sqlite_uri(db_path, "ro"), uri=True)

    conn.row_factory = sqlite3.Row
    conn.execute("PRAGMA foreign_keys = ON")
    if readonly:
        conn.execute("PRAGMA query_only = ON")
    return conn


def open_readonly_database(path: Path) -> sqlite3.Connection:
    return open_database(path, readonly=True)


def enable_wal(conn: sqlite3.Connection) -> str:
    row = conn.execute("PRAGMA journal_mode = WAL").fetchone()
    return str(row[0]).lower()


def load_sqlite_vec(conn: sqlite3.Connection) -> str:
    try:
        import sqlite_vec  # noqa: PLC0415

        conn.enable_load_extension(True)
        sqlite_vec.load(conn)
        row = conn.execute("SELECT vec_version()").fetchone()
        return str(row[0])
    except Exception as exc:  # pragma: no cover - message path depends on local SQLite build
        raise SqliteVecUnavailableError(
            "sqlite-vec could not be loaded. Verify the sqlite-vec package is installed "
            "and this Python build allows SQLite extension loading."
        ) from exc
    finally:
        with suppress(sqlite3.Error):
            conn.enable_load_extension(False)


def ensure_migrations_table(conn: sqlite3.Connection) -> None:
    conn.execute("""
        CREATE TABLE IF NOT EXISTS schema_migrations (
          version TEXT PRIMARY KEY,
          applied_at TIMESTAMP NOT NULL DEFAULT CURRENT_TIMESTAMP
        )
        """)
    conn.commit()


def applied_migrations(conn: sqlite3.Connection) -> set[str]:
    ensure_migrations_table(conn)
    rows = conn.execute("SELECT version FROM schema_migrations").fetchall()
    return {str(row["version"]) for row in rows}


def migration_files() -> list[Path]:
    return sorted(MIGRATIONS_DIR.glob("*.sql"))


def apply_migrations(conn: sqlite3.Connection) -> list[str]:
    applied = applied_migrations(conn)
    newly_applied: list[str] = []

    for migration in migration_files():
        version = migration.stem
        if version in applied:
            continue

        sql = migration.read_text(encoding="utf-8")
        conn.executescript(sql)
        conn.execute("INSERT INTO schema_migrations (version) VALUES (?)", (version,))
        conn.commit()
        newly_applied.append(version)

    return newly_applied


def initialize_database(
    path: Path,
    *,
    require_sqlite_vec: bool = True,
) -> DatabaseInitResult:
    conn = open_database(path)
    try:
        journal_mode = enable_wal(conn)
        sqlite_vec_version: str | None = None
        if require_sqlite_vec:
            sqlite_vec_version = load_sqlite_vec(conn)
        migrations_applied = apply_migrations(conn)
    finally:
        conn.close()

    return DatabaseInitResult(
        db_path=path.expanduser().resolve(),
        journal_mode=journal_mode,
        sqlite_vec_version=sqlite_vec_version,
        migrations_applied=migrations_applied,
    )


def list_user_tables(conn: sqlite3.Connection) -> list[str]:
    rows = conn.execute("""
        SELECT name
        FROM sqlite_master
        WHERE type IN ('table', 'view')
          AND name NOT LIKE 'sqlite_%'
        ORDER BY name
        """).fetchall()
    return [str(row["name"]) for row in rows]
