from __future__ import annotations

from ad_classifier.agent.schema import render_schema_summary


def test_schema_summary_includes_main_tables(readonly_conn):
    summary = render_schema_summary(readonly_conn)
    assert "ads(" in summary
    assert "campaigns(" in summary
    assert "classifications(" in summary
    assert "marketing_entities(" in summary
    assert "agent_sessions(" in summary


def test_schema_summary_excludes_fts_and_vector_shadows(readonly_conn):
    summary = render_schema_summary(readonly_conn)
    # FTS5 shadow tables and sqlite-vec virtual tables must be hidden — the
    # agent uses dedicated tools for those.
    assert "ads_fts_data" not in summary
    assert "vec_ads_text" not in summary
    assert "schema_migrations" not in summary
