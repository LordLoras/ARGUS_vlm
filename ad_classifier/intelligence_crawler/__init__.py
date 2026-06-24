"""Intelligence crawler: brand-anchored awareness of new US ad/campaign releases.

This is a separate, complementary system to the entity-graph crawler
(``ad_classifier/entity_graph/crawler.py``). Where that crawler starts from a
submitted ad and verifies product/brand facts, this one starts from a *watchlist of
US brands* and polls trusted sources to detect when a brand publishes something new
("Toyota appears to have released a new campaign/ad").

Design rules (see docs/ runbook):
- Own store ``intelligence_crawler.db``; reads submitted/graph data read-only only.
- Every external source sits behind a :class:`SourceAdapter` interface with a mock, so
  the test suite runs with no network, no API keys, and no GPU.
- New sources are added by registering one adapter class — the runner depends only on
  the interface, never on a concrete source.
- US market only; candidate-by-default; nothing is presented as fact without evidence.
"""

from ad_classifier.intelligence_crawler.config import IntelConfig, load_intel_config

__all__ = ["IntelConfig", "load_intel_config"]
