from __future__ import annotations

from ad_classifier.intelligence_crawler.config import load_intel_config

YAML = """
enabled: true
db_path: ./intel.db
cache_dir: ./cache
watchlist:
  include_graph_brands: false
  entity_graph_db_path: null
  seed_brands: [Toyota, Ford]
sources:
  - id: s1
    brand: Toyota
    source_type: mock
    tier: A
    enabled: false
  - id: s2
    brand: Ford
    source_type: rss
    tier: B
    enabled: true
    url: https://example.com/feed
"""


def test_paths_resolve_relative_to_yaml(tmp_path, monkeypatch):
    path = tmp_path / "intelligence_crawler.yaml"
    path.write_text(YAML, encoding="utf-8")
    # Load from a different CWD to prove resolution is yaml-relative, not CWD-relative.
    monkeypatch.chdir(tmp_path.parent)
    cfg = load_intel_config(path)
    assert cfg.db_path == (tmp_path / "intel.db").resolve()
    assert cfg.cache_dir == (tmp_path / "cache").resolve()


def test_disabled_by_default_and_lookups(tmp_path):
    path = tmp_path / "intelligence_crawler.yaml"
    path.write_text(YAML, encoding="utf-8")
    cfg = load_intel_config(path)
    enabled = cfg.enabled_sources()
    assert [s.id for s in enabled] == ["s2"]  # only the explicitly enabled one
    assert cfg.source_by_id("s1") is not None
    assert cfg.source_by_id("s2").tier == "C"
    assert cfg.source_by_id("missing") is None


def test_missing_file_returns_defaults(tmp_path):
    cfg = load_intel_config(tmp_path / "nope.yaml")
    assert cfg.sources == []
    assert cfg.market == "US"
