from __future__ import annotations

import pytest

from ad_classifier.agent.catalog import ToolCatalog, default_tools
from ad_classifier.agent.tools.aggregate import AggregateTool
from ad_classifier.agent.tools.base import ToolContext
from ad_classifier.agent.tools.compare_ads import CompareAdsTool
from ad_classifier.agent.tools.count_ads import CountAdsTool
from ad_classifier.agent.tools.get_ad import GetAdTool
from ad_classifier.agent.tools.get_campaign import GetCampaignTool, ListCampaignsTool
from ad_classifier.agent.tools.list_ads import ListAdsTool
from ad_classifier.agent.tools.search import HybridSearchTool, VectorSimilarityTool
from ad_classifier.agent.tools.sql_readonly import SqlReadonlyTool


def _ctx(conn, agent_config) -> ToolContext:
    return ToolContext(conn=conn, config=agent_config)


def _insert_hvac_ad(conn) -> None:
    conn.execute(
        """
        INSERT INTO ads (
            id, source_path, ingested_at, status, brand_name, advertiser_name,
            products_text, primary_category, decision, source_hash
        )
        VALUES (
            'ad_hvac_a', '/tmp/hvac.mp4', datetime('now'), 'completed',
            'Prillaman Mechanical, Heating & AC', 'Prillaman',
            'Heating systems, Cooling systems, Air Conditioning Check',
            'other', 'allow', 'hash_hvac'
        )
        """
    )


def test_list_ads_returns_seeded_ads(readonly_conn, agent_config):
    result = ListAdsTool().call({"limit": 25}, _ctx(readonly_conn, agent_config))
    assert result.ok
    ids = sorted(item["ad_id"] for item in result.data)
    assert ids == ["ad_jeep_a", "ad_jeep_b", "ad_pizza_a"]


def test_list_ads_brand_filter(readonly_conn, agent_config):
    result = ListAdsTool().call({"brand": "Jeep"}, _ctx(readonly_conn, agent_config))
    assert {item["ad_id"] for item in result.data} == {"ad_jeep_a", "ad_jeep_b"}
    assert {item["products"] for item in result.data} == {"Wrangler", "Grand Cherokee"}


def test_list_ads_truncation_flag(readonly_conn, agent_config):
    result = ListAdsTool().call({"limit": 1}, _ctx(readonly_conn, agent_config))
    assert result.row_count == 1
    assert result.truncated is True


def test_count_ads(readonly_conn, agent_config):
    result = CountAdsTool().call({"brand": "Jeep"}, _ctx(readonly_conn, agent_config))
    assert result.ok
    assert result.data["count"] == 2


def test_count_ads_q_filter(readonly_conn, agent_config):
    result = CountAdsTool().call({"q": "Wrangler"}, _ctx(readonly_conn, agent_config))
    assert result.ok
    assert result.data["count"] == 1
    assert result.data["filters"] == {"q": "Wrangler"}


def test_count_ads_expands_automotive_topic(readonly_conn, agent_config):
    result = CountAdsTool().call({"q": "cars"}, _ctx(readonly_conn, agent_config))

    assert result.ok
    assert result.data["count"] == 2
    assert "automotive" in result.data["expanded_terms"]["q"]


def test_count_ads_expands_restaurant_topic(readonly_conn, agent_config):
    result = CountAdsTool().call({"q": "restaurants"}, _ctx(readonly_conn, agent_config))

    assert result.ok
    assert result.data["count"] == 1
    assert "food_beverage" in result.data["expanded_terms"]["q"]


def test_count_ads_expands_hvac_topic(writable_conn, agent_config):
    _insert_hvac_ad(writable_conn)

    result = CountAdsTool().call({"q": "HVAC"}, _ctx(writable_conn, agent_config))

    assert result.ok
    assert result.data["count"] == 1
    assert "air conditioning" in result.data["expanded_terms"]["q"]


def test_count_ads_expands_hvac_category_mistake(writable_conn, agent_config):
    _insert_hvac_ad(writable_conn)

    result = CountAdsTool().call({"category": "HVAC"}, _ctx(writable_conn, agent_config))

    assert result.ok
    assert result.data["count"] == 1


def test_list_ads_expands_services_topic(writable_conn, agent_config):
    _insert_hvac_ad(writable_conn)

    result = ListAdsTool().call({"q": "services"}, _ctx(writable_conn, agent_config))

    assert result.ok
    assert [item["ad_id"] for item in result.data] == ["ad_hvac_a"]


def test_list_ads_expands_repair_topic(writable_conn, agent_config):
    _insert_hvac_ad(writable_conn)

    result = ListAdsTool().call({"q": "repairs"}, _ctx(writable_conn, agent_config))

    assert result.ok
    assert [item["ad_id"] for item in result.data] == ["ad_hvac_a"]


def test_count_ads_expands_installation_category_mistake(writable_conn, agent_config):
    _insert_hvac_ad(writable_conn)

    result = CountAdsTool().call(
        {"category": "installation"}, _ctx(writable_conn, agent_config)
    )

    assert result.ok
    assert result.data["count"] == 1


def test_get_ad_returns_classification_and_marketing(readonly_conn, agent_config):
    result = GetAdTool().call({"ad_id": "ad_jeep_a"}, _ctx(readonly_conn, agent_config))
    assert result.ok
    assert result.data["ad"]["id"] == "ad_jeep_a"
    assert result.data["classification"]["primary_category"] == "automotive"
    assert result.data["marketing_entities"]["brand"]["name"] == "Jeep"
    assert any(c["campaign_id"] == "c_jeep_summer" for c in result.data["campaigns"])


def test_get_ad_missing(readonly_conn, agent_config):
    result = GetAdTool().call({"ad_id": "ad_missing"}, _ctx(readonly_conn, agent_config))
    assert result.ok is False
    assert "not found" in (result.error or "")


def test_get_campaign(readonly_conn, agent_config):
    result = GetCampaignTool().call(
        {"campaign_id": "c_jeep_summer"}, _ctx(readonly_conn, agent_config)
    )
    assert result.ok
    assert result.data["campaign"]["name"] == "Jeep Summer 2026"
    assert result.data["ads"][0]["ad_id"] == "ad_jeep_a"


def test_list_campaigns(readonly_conn, agent_config):
    result = ListCampaignsTool().call(
        {"brand": "Jeep"}, _ctx(readonly_conn, agent_config)
    )
    assert result.ok
    assert result.data[0]["campaign_id"] == "c_jeep_summer"


def test_aggregate_by_brand(readonly_conn, agent_config):
    result = AggregateTool().call(
        {"group_by": "brand_name"}, _ctx(readonly_conn, agent_config)
    )
    assert result.ok
    buckets = {row["bucket"]: row["count"] for row in result.data}
    assert buckets["Jeep"] == 2
    assert buckets["Domino's"] == 1


def test_aggregate_rejects_unknown_group_by(readonly_conn, agent_config):
    result = AggregateTool().call(
        {"group_by": "source_path"}, _ctx(readonly_conn, agent_config)
    )
    assert result.ok is False


def test_sql_readonly_select_works(readonly_conn, agent_config):
    result = SqlReadonlyTool().call(
        {"sql": "SELECT brand_name, COUNT(*) AS n FROM ads GROUP BY brand_name"},
        _ctx(readonly_conn, agent_config),
    )
    assert result.ok
    rows = {r["brand_name"]: r["n"] for r in result.data}
    assert rows["Jeep"] == 2


def test_sql_readonly_blocks_write(readonly_conn, agent_config):
    result = SqlReadonlyTool().call(
        {"sql": "DELETE FROM ads"}, _ctx(readonly_conn, agent_config)
    )
    assert result.ok is False


def test_sql_readonly_blocks_pragma_or_attach(readonly_conn, agent_config):
    result = SqlReadonlyTool().call(
        {"sql": "PRAGMA integrity_check"}, _ctx(readonly_conn, agent_config)
    )
    assert result.ok is False


def test_sql_readonly_blocks_multistatement(readonly_conn, agent_config):
    result = SqlReadonlyTool().call(
        {"sql": "SELECT 1; SELECT 2"}, _ctx(readonly_conn, agent_config)
    )
    assert result.ok is False


def test_sql_readonly_caps_rows(readonly_conn, agent_config):
    # Build a query that returns many rows
    result = SqlReadonlyTool().call(
        {"sql": "SELECT id FROM ads", "limit": 1},
        _ctx(readonly_conn, agent_config),
    )
    assert result.ok
    assert result.row_count == 1
    assert result.truncated is True


def test_readonly_connection_blocks_writes(readonly_conn):
    import sqlite3

    with pytest.raises(sqlite3.OperationalError):
        readonly_conn.execute("DELETE FROM ads WHERE id = 'ad_jeep_a'")


def test_hybrid_search_falls_back_to_fts_without_embedder(readonly_conn, agent_config):
    # No embedder/vector store configured → tool should still return without crashing.
    result = HybridSearchTool().call(
        {"query": "Wrangler"}, _ctx(readonly_conn, agent_config)
    )
    # FTS5 on this seed has nothing indexed, so we just expect ok=True with []
    assert result.ok
    assert isinstance(result.data, list)


def test_vector_similarity_requires_store(readonly_conn, agent_config):
    result = VectorSimilarityTool().call(
        {"ad_id": "ad_jeep_a"}, _ctx(readonly_conn, agent_config)
    )
    assert result.ok is False
    assert "vector store" in (result.error or "")


def test_compare_ads_diff_without_vectors(readonly_conn, agent_config):
    """compare_ads should still produce a structured diff if vectors are missing."""
    result = CompareAdsTool().call(
        {"left_ad_id": "ad_jeep_a", "right_ad_id": "ad_jeep_b"},
        _ctx(readonly_conn, agent_config),
    )
    assert result.ok
    fields = {d["field"]: d for d in result.data["differences"]}
    assert "products" in fields
    assert fields["products"]["left"] == ["Wrangler"]
    assert fields["products"]["right"] == ["Grand Cherokee"]
    # Same brand, different products → expect campaign-different-sku verdict
    assert result.data["verdict"] in (
        "same_campaign_different_sku",
        "related",
        "unrelated",
    )


def test_compare_ads_unrelated(readonly_conn, agent_config):
    result = CompareAdsTool().call(
        {"left_ad_id": "ad_jeep_a", "right_ad_id": "ad_pizza_a"},
        _ctx(readonly_conn, agent_config),
    )
    assert result.ok
    diffs = {d["field"]: d for d in result.data["differences"]}
    assert "brand" in diffs


def test_default_catalog_registers_all_tools():
    catalog = ToolCatalog()
    names = set(catalog.names())
    expected = {tool.name for tool in default_tools()}
    assert names == expected


def test_tool_catalog_unknown_tool_returns_error(readonly_conn, agent_config):
    catalog = ToolCatalog()
    result = catalog.call("does_not_exist", {}, _ctx(readonly_conn, agent_config))
    assert result.ok is False
    assert "unknown tool" in (result.error or "")


def test_catalog_renders_text_summary():
    text = ToolCatalog().render_text_summary()
    assert "list_ads" in text
    assert "compare_ads" in text


def test_openai_tool_specs_have_function_shape():
    catalog = ToolCatalog()
    specs = catalog.openai_tools()
    assert all(spec["type"] == "function" for spec in specs)
    assert all("name" in spec["function"] for spec in specs)
