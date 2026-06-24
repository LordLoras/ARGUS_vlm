"""Source adapters for the intelligence crawler.

Importing this package registers the built-in adapters in the registry (see
``base.py``). Add a new source by creating a module here with a
``@register_source("your_type")``-decorated adapter class and importing it below.
"""

from ad_classifier.intelligence_crawler.sources import base, rss, youtube  # noqa: F401

__all__ = ["base", "rss", "youtube"]
