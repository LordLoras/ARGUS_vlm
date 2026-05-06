from __future__ import annotations

from typer.testing import CliRunner

from ad_classifier.cli import app

runner = CliRunner()


def test_help_lists_init_db():
    result = runner.invoke(app, ["--help"])

    assert result.exit_code == 0
    assert "dedup-check" in result.output
    assert "init-db" in result.output
    assert "ingest" in result.output
    assert "version" in result.output


def test_init_db_cli_creates_database(tmp_path):
    db_path = tmp_path / "cli.db"

    result = runner.invoke(app, ["init-db", "--db-path", str(db_path)])

    assert result.exit_code == 0, result.output
    assert db_path.exists()
    assert "journal_mode=wal" in result.output
    assert "sqlite_vec=" in result.output
