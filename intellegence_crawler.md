# Intelligence Crawler v2 Plan

Status: planning draft for review by other models and future implementation.

Date: 2026-06-24

Repository context: `C:\Users\moonk\Desktop\ads_classification`

Note on filename: this file intentionally uses the requested spelling, `intellegence_crawler.md`.

## 1. Executive Summary

The project should add a separate intelligence crawler module whose job is to discover and track public internet signals about digital versions of TV ads and campaign launches. The crawler should not classify ads directly, mutate submitted ad records, or act as a broad web scraper. It should collect candidate ad/campaign signals from reliable sources, preserve provenance, deduplicate them, score confidence, and expose the signals to the existing pipeline, campaign research, entity graph, and natural-language agent.

The recommended implementation is a new module, tentatively:

```text
ad_classifier/intelligence_crawler/
```

with its own local SQLite database, tentatively:

```text
intelligence_crawler.db
```

The crawler's main output should be statements like:

```text
Toyota appears to have released a new digital ad/campaign.
Evidence:
- official Toyota YouTube upload
- Toyota pressroom article
- matching campaign phrase on official landing page
- optional trade press corroboration
Confidence: 0.87
Status: corroborated candidate
```

The crawler should be source-registry driven. It should crawl known official sources first, use public APIs where available, use RSS/sitemaps before full HTML crawling, and treat broad web search as weak discovery only. Every extracted claim must retain provenance.

## 2. Why This Should Be Separate From the Existing Entity Crawler

The current repository already has an experimental entity crawler under `ad_classifier/entity_graph/`. That crawler is useful, but its purpose is different:

- It starts from submitted ads and product/entity mentions.
- It crawls product or brand pages to enrich the product entity graph.
- It writes candidate-only graph facts.
- It is connected to product/brand/category/taxonomy relation discovery.

The v2 intelligence crawler should start from public sources and produce campaign/ad-event intelligence:

- "A new ad was uploaded."
- "A campaign launch appears to have happened."
- "This digital video may be the online version of a TV spot."
- "This public campaign signal may match an existing local ad/campaign."
- "This brand has a new creative variant, offer, or product push."

Those are different data products. Keeping the module separate avoids confusing product-entity discovery with ad/campaign monitoring.

## 3. Goals

The crawler should:

1. Discover digital versions of TV ads and related campaign assets.
2. Detect likely new campaign launches or new creative variants.
3. Prefer official or high-provenance sources over generic web search.
4. Persist every signal locally with source evidence.
5. Support incremental, restartable crawling.
6. Deduplicate URLs, platform IDs, media assets, and semantically similar signals.
7. Match discovered signals to existing local `ads`, `campaigns`, and entity graph records.
8. Integrate with campaign research without doing live web browsing inline.
9. Support local-first operation and tests without network, GPU, or paid services.
10. Keep all crawler outputs as candidate/corroborated intelligence, not authoritative mutations.

## 4. Non-Goals

The crawler should not:

1. Become a general-purpose internet crawler.
2. Bypass robots.txt, paywalls, login walls, anti-bot systems, or platform restrictions.
3. Scrape search engine result pages as the main discovery system.
4. Auto-download media where source terms or user rights are unclear.
5. Mutate submitted ad/classification/campaign records directly.
6. Replace the existing ingest/classification pipeline.
7. Perform content moderation, blocking, escalation, or human-review decisioning.
8. Make claims without source evidence.
9. Treat third-party articles as authoritative proof of brand/product facts by themselves.
10. Depend on cloud services by default.

## 5. Terminology

### Source

A monitored origin of data, such as an official Toyota YouTube channel, Toyota pressroom RSS feed, a brand sitemap, or a platform ad-library endpoint.

### Resource

A fetched item from a source, such as a YouTube video record, RSS item, webpage, sitemap URL, press release, or platform ad-library creative record.

### Signal

A structured candidate observation derived from one or more resources. Examples:

- `new_ad_upload`
- `campaign_launch`
- `new_campaign_variant`
- `offer_change`
- `product_push`
- `creative_reuse`
- `ad_library_seen`
- `official_press_mention`

### Evidence

The exact source-backed facts behind a signal: URLs, titles, snippets, dates, platform IDs, hashes, thumbnails, transcript excerpts, extracted metadata, and parser confidence.

### Match

A link from a crawler signal to existing local data: `ad_id`, `campaign_id`, product node, brand node, or taxonomy mapping.

## 6. Reliability Philosophy

Reliability should be based on source quality, extraction quality, corroboration, and local matching. The crawler should never say "Toyota released a campaign" merely because a generic search result mentions Toyota and an ad.

Suggested source tiers:

| Tier | Source type | Reliability role |
|---|---|---|
| A | Brand-owned official YouTube channels | Strong evidence for video/ad publication |
| A | Brand-owned pressrooms, RSS feeds, sitemaps, campaign pages | Strong evidence for campaign/product launch context |
| A | First-party social/video accounts where APIs or stable feeds are available | Strong evidence if source identity is confirmed |
| B | Official ad-library APIs and transparency datasets | Strong evidence that an ad ran, but coverage varies by region/platform |
| B | Agency or production company case studies | Useful campaign naming/creative context; needs corroboration |
| C | Trade press and ad-industry publications | Useful corroboration and campaign narrative; not authoritative alone |
| C | Internet Archive or public video archives | Useful historical discovery; needs source/date care |
| D | General web search results | Discovery only; should not confirm by itself |

Signals should be explicitly labeled by status:

- `candidate`: one or more weak or unverified signals exist.
- `corroborated`: strong single official source or multiple independent sources support it.
- `matched_local`: signal has a meaningful match to local ad/campaign/entity records.
- `accepted`: analyst accepted the signal.
- `dismissed`: analyst dismissed the signal.
- `stale`: signal is old or superseded.

These statuses are operational intelligence statuses, not content-policy decisions.

## 7. Current Repo Integration Points

Useful existing patterns and integration points:

1. Existing entity crawler:
   - `ad_classifier/entity_graph/crawler.py`
   - `ad_classifier/entity_graph/crawler_config.py`
   - `entity_crawler.yaml`
   - It already has useful concepts: config-driven crawling, cache directories, robots handling, rate limits, crawler runs, candidate-only writes, VLM-assisted parsing.

2. Campaign research:
   - `ad_classifier/campaigns/research_deep.py`
   - Current deep research carries `include_web`, but returns `web_available: false`.
   - This is a natural future integration point. `include_web=true` should read stored crawler signals, not perform live crawling during an analyst request.

3. Existing ad/campaign data:
   - `ads`
   - `campaigns`
   - `ad_campaigns`
   - `marketing_entities`
   - `classifications`
   - `frames`
   - `ocr_items`
   - `transcript_segments`

4. Existing similarity and retrieval:
   - file hash
   - perceptual hash
   - text embeddings
   - visual embeddings
   - hybrid search
   - RRF

5. Existing entity graph:
   - Should be read-only input for matching.
   - Crawler signals may point to graph nodes, but should not directly confirm graph facts without existing review rules.

## 8. Proposed Module Boundary

Suggested package tree:

```text
ad_classifier/
  intelligence_crawler/
    __init__.py
    config.py
    models.py
    schema.py
    repository.py
    runner.py
    scheduler.py
    source_registry.py
    fetch/
      __init__.py
      http.py
      robots.py
      cache.py
      browser.py
    adapters/
      __init__.py
      base.py
      youtube.py
      rss.py
      sitemap.py
      pressroom.py
      webpage.py
      meta_ad_library.py
      tiktok_commercial_content.py
      internet_archive.py
      trade_press.py
      search_provider.py
    extraction/
      __init__.py
      metadata.py
      structured_data.py
      campaign_terms.py
      video_signals.py
      date_parsing.py
      brand_match.py
    scoring/
      __init__.py
      reliability.py
      confidence.py
      corroboration.py
    dedup/
      __init__.py
      canonical_url.py
      resource_hash.py
      media_hash.py
      signal_merge.py
    matching/
      __init__.py
      local_ads.py
      campaigns.py
      entity_graph.py
      embeddings.py
    tools/
      __init__.py
      list_signals.py
      explain_signal.py
      match_signal.py
    api/
      __init__.py
      routes.py
    cli.py
```

The implementation can be smaller initially, but this boundary keeps adapters, extraction, scoring, dedup, and local matching independent.

## 9. Proposed Configuration

Create a separate config file:

```text
intelligence_crawler.yaml
```

Example:

```yaml
enabled: true
db_path: ./intelligence_crawler.db
cache_dir: ./data/intelligence_crawler_cache

crawler:
  respect_robots_txt: true
  timeout_s: 12
  max_page_bytes: 2000000
  rate_limit_per_minute: 20
  max_resources_per_source: 100
  user_agent: "ARGUS-IntelligenceCrawler/0.1 (+local analyst tool)"
  store_raw_html: false
  browser_fallback: false

sources:
  - id: toyota_youtube
    brand: Toyota
    type: youtube_channel
    tier: A
    enabled: true
    channel_id: "..."
    poll_interval_hours: 12

  - id: toyota_pressroom
    brand: Toyota
    type: rss_or_sitemap
    tier: A
    enabled: true
    url: "https://..."
    poll_interval_hours: 12

adapters:
  youtube:
    enabled: true
    api_key_env: YOUTUBE_API_KEY
    use_uploads_playlist: true
    use_search_list: false

  meta_ad_library:
    enabled: false
    access_token_env: META_AD_LIBRARY_TOKEN
    regions: []

  tiktok_commercial_content:
    enabled: false
    client_key_env: TIKTOK_CLIENT_KEY

scoring:
  corroborated_min_confidence: 0.75
  matched_local_min_confidence: 0.70
  source_weights:
    official_brand: 0.45
    official_video_platform: 0.40
    ad_library: 0.35
    agency_case_study: 0.25
    trade_press: 0.20
    general_search: 0.05
```

Config should support a source registry rather than hardcoding brands in Python.

## 10. Source Adapter Plan

### 10.1 YouTube Official Channel Adapter

This should be the first adapter because it is structured and high-value.

Preferred approach:

1. Store official brand channel IDs in the source registry.
2. Resolve the channel's uploads playlist using YouTube Data API `channels.list`.
3. Poll the uploads playlist with `playlistItems.list`.
4. Fetch video metadata with `videos.list` only when needed for duration/statistics/topic details.
5. Avoid broad `search.list` except for source bootstrapping or explicit analyst queries.

Why:

- Official channel uploads are a strong signal.
- Playlist polling is incremental and relatively cheap.
- Platform IDs provide stable deduplication keys.
- Titles/descriptions/published dates are structured.

Detected signal examples:

- `new_ad_upload`
- `new_campaign_video`
- `campaign_name_observed`
- `product_push`
- `seasonal_offer`
- `creative_variant`

Fields to extract:

- platform video ID
- channel ID
- title
- description
- published_at
- thumbnails
- duration
- tags if available
- default language
- view count if available and useful
- URL
- canonical brand/channel source ID

Potential query terms for classification of uploads:

- "commercial"
- "ad"
- "spot"
- "campaign"
- "launch"
- "introducing"
- "event"
- "sale"
- model/product names
- campaign phrase repetition across videos

Important caution:

Not every official YouTube upload is an ad. Some are how-to videos, event recaps, interviews, owner education, or social content. The adapter should produce candidate video resources first, then extraction/scoring should decide whether it looks ad-like.

### 10.2 Brand Pressroom RSS/Sitemap Adapter

This should be the second adapter.

Preferred approach:

1. Poll RSS/Atom feeds when available.
2. Poll XML sitemaps and sitemap indexes.
3. Prefer `news`, `press`, `media`, `campaign`, and `video` sections.
4. Use `lastmod`, RSS GUIDs, and content hashes for incremental updates.
5. Extract OpenGraph, Twitter Card, JSON-LD, Schema.org `Article`, `NewsArticle`, `VideoObject`, and `Organization` metadata.

Detected signal examples:

- `campaign_launch`
- `product_launch`
- `official_press_mention`
- `new_offer_or_sales_event`
- `campaign_video_embedded`

Fields to extract:

- title
- description
- publication date
- canonical URL
- article text excerpt
- brand
- product names
- campaign names
- embedded video URLs
- image URLs
- structured-data entities

Important caution:

A product announcement is not necessarily an ad campaign. The crawler should distinguish:

- product news
- corporate news
- sales event
- campaign launch
- ad creative release

### 10.3 Official Campaign/Landing Page Adapter

This adapter should crawl only configured first-party domains and selected URLs discovered from official sources.

Preferred approach:

1. Start from known official domains.
2. Use sitemaps and official links.
3. Do shallow crawling only.
4. Respect robots.txt.
5. Avoid form flows, dynamic shopping pages, account pages, and dealer inventory pages unless explicitly configured.

Useful signals:

- campaign landing pages
- current offers
- model/product push
- reused campaign phrase
- video embeds
- CTA language

Fields to extract:

- visible title/headings
- meta description
- OpenGraph data
- JSON-LD
- CTA phrases
- offer text
- disclaimer snippets
- embedded videos
- canonical URL

### 10.4 Platform Ad Library Adapters

These should be optional and disabled by default.

Potential adapters:

- Meta Ad Library API
- TikTok Commercial Content API
- Google Ads Transparency Center if a supported access path is chosen later

Use cases:

- confirm paid creative is/was active
- gather ad text and public creative metadata
- detect regional/platform-specific variants

Important caution:

Coverage varies by platform, region, category, and API access. For example, political/social issue ad coverage is different from general commercial ad coverage. The crawler must store source coverage limitations in the evidence payload.

### 10.5 Agency and Production Company Adapter

Agency case studies often reveal campaign names and creative strategy.

Use cases:

- campaign names
- launch windows
- creative themes
- production credits
- related variants

Reliability:

- Good for campaign context.
- Not enough by itself to confirm active public release.
- Should corroborate with official brand/video/ad-library signals.

### 10.6 Trade Press Adapter

Trade press is valuable for corroboration and context.

Potential sources:

- Ad Age
- Adweek
- The Drum
- Campaign
- Ads of the World
- Little Black Book

Use cases:

- campaign launch reporting
- agency of record
- creative concept
- release dates
- market/geography

Reliability:

- Corroboration only unless the article embeds official creative or links to official sources.

### 10.7 Internet Archive / Public Archive Adapter

This should be optional.

Use cases:

- historical TV ad references
- older campaign assets
- broadcast-ad archives if available

Caution:

- Metadata quality varies.
- Rights and provenance need careful treatment.
- Use as discovery/corroboration, not automatic ground truth.

### 10.8 General Search Provider Adapter

This should be a weak discovery layer only.

Acceptable uses:

- find candidate official pages for a configured brand
- discover source URLs for manual review
- bootstrap source registry entries

Avoid:

- scraping search result HTML as the main pipeline
- treating search snippets as authoritative evidence
- high-volume search polling

If using a search API, make it an optional adapter with explicit credentials and limits.

## 11. Crawler Pipeline

Recommended stage sequence:

```text
1. Load source registry
2. Select due sources
3. Fetch source resources incrementally
4. Normalize and cache fetched resources
5. Extract structured metadata
6. Generate candidate signals
7. Deduplicate resources and signals
8. Score source reliability and signal confidence
9. Corroborate across sources
10. Match against local ads/campaigns/entities
11. Persist all evidence and matches
12. Expose review/API/agent outputs
```

### Stage 1: Load Source Registry

The source registry should include:

- source ID
- brand
- source type
- reliability tier
- base URL or platform ID
- allowed domains
- poll interval
- adapter settings
- optional products or business units
- optional geographic scope
- notes and provenance for why the source is trusted

### Stage 2: Select Due Sources

Use per-source polling metadata:

- `last_success_at`
- `last_attempt_at`
- `next_due_at`
- `last_error`
- `consecutive_errors`
- `etag`
- `last_modified`
- `watermark`

### Stage 3: Fetch Incrementally

For HTTP:

- use conditional requests with ETag and Last-Modified
- store response metadata
- cap bytes
- rate limit per domain/source
- follow redirects carefully
- record final URL
- respect robots.txt

For APIs:

- store page tokens or date watermarks
- back off on quota/rate limits
- persist raw JSON payloads if small and allowed

### Stage 4: Normalize and Cache

Normalize:

- canonical URL
- domain
- query parameters
- platform IDs
- dates
- language
- content type
- content hash

Cache:

- raw JSON or selected fields
- raw HTML only if config allows
- text extraction result
- structured metadata extraction result

### Stage 5: Extract Metadata

Extract:

- title
- description
- canonical URL
- OpenGraph
- Twitter Card
- JSON-LD
- Schema.org entities
- RSS item fields
- YouTube metadata
- visible headings
- article body excerpt
- embedded video/image URLs
- dates
- brand/product/campaign phrase candidates

### Stage 6: Generate Candidate Signals

Signal generation should be deterministic first:

- official video published recently and title/description looks ad-like
- official pressroom article mentions "campaign", "commercial", "spot", "launch", "new ad", "brand campaign"
- same campaign phrase appears in multiple official resources
- official landing page and YouTube upload share a phrase/product/date window
- ad library creative text matches official campaign phrase

LLM/VLM use should be optional:

- local Gemma can summarize/extract campaign facts from official snippets
- local VLM can inspect thumbnails or downloaded frames only if media use is allowed
- all model outputs remain candidate facts with provenance

### Stage 7: Deduplicate

Deduplicate at multiple levels:

Resource-level:

- canonical URL
- platform ID
- content hash
- normalized title + date

Media-level:

- video ID
- thumbnail perceptual hash
- optional downloaded media hash
- optional sampled-frame pHash if media is available

Signal-level:

- brand + campaign phrase + source date window
- brand + product + event type + date window
- shared official URL or video ID
- semantic similarity of signal text

### Stage 8: Score Confidence

Confidence should be explainable. Suggested components:

```text
confidence =
  source_reliability
  + brand_identity_confidence
  + ad_likeness_score
  + campaign_phrase_score
  + media_evidence_score
  + corroboration_score
  + local_match_score
  - penalties
```

Example factors:

Source reliability:

- official brand source: high
- official platform ad library: medium/high depending coverage
- agency case study: medium
- trade press: medium/low
- general search: low

Brand identity:

- known official channel/domain: high
- verified source registry match: high
- inferred from page text only: lower

Ad-likeness:

- title includes "commercial", "ad", "spot", "campaign"
- short video duration typical of ads
- description mentions TV, broadcast, campaign, or creative
- video has product/offer/CTA language

Campaign phrase:

- repeated phrase across resources
- appears in official press and video title/description
- appears in existing local campaign suggestions

Media evidence:

- official video exists
- thumbnail/video extracted
- duration known
- optional visual/text embedding match to local ads

Corroboration:

- multiple independent sources
- official source plus ad library
- official source plus trade press

Penalties:

- source is unofficial
- source has no date
- source is old
- source is dealer/local reseller instead of brand
- page is corporate/product news, not ad/campaign
- title suggests non-ad content such as tutorial, owner guide, earnings, job post

### Stage 9: Corroborate

Corroboration rules should be explicit.

Examples:

- One official brand YouTube upload can be enough for `new_ad_upload`.
- One official pressroom article can be enough for `official_press_mention`.
- `campaign_launch` should preferably require either:
  - an official pressroom/campaign page explicitly using campaign language, or
  - official video plus matching official page/pressroom text, or
  - official video plus ad-library/trade corroboration.

### Stage 10: Match Against Local Data

Match signals to local data through:

- brand exact/alias matching
- product/entity graph matching
- campaign suggestion phrase matching
- text embedding similarity
- visual embedding similarity if media/frame evidence exists
- pHash similarity if media/frame evidence exists
- date proximity to local ingest time
- local classification category proximity

Output examples:

```json
{
  "signal_id": "sig_toyota_2026_001",
  "matched_local_ads": [
    {
      "ad_id": "ad_abc123",
      "match_score": 0.82,
      "reasons": [
        "same brand",
        "campaign phrase overlap",
        "visual embedding similarity",
        "product match"
      ]
    }
  ],
  "matched_campaigns": [
    {
      "campaign_id": "c_toyota_summer_event",
      "match_score": 0.76
    }
  ]
}
```

### Stage 11: Persist Everything

Persistence should be transactional and audit-friendly.

No signal should exist without evidence.

### Stage 12: Expose Outputs

Expose:

- API endpoints
- CLI commands
- read-only agent tools
- optional frontend review page later

## 12. Proposed Database Schema

The exact schema should be implemented through migrations, but these are the core concepts.

### `intel_sources`

```sql
CREATE TABLE intel_sources (
  id TEXT PRIMARY KEY,
  brand_name TEXT NOT NULL,
  source_type TEXT NOT NULL,
  tier TEXT NOT NULL,
  url TEXT,
  platform TEXT,
  platform_id TEXT,
  enabled INTEGER NOT NULL DEFAULT 1,
  poll_interval_hours REAL NOT NULL DEFAULT 24,
  allowed_domains_json TEXT NOT NULL DEFAULT '[]',
  config_json TEXT NOT NULL DEFAULT '{}',
  notes TEXT,
  created_at TEXT NOT NULL,
  updated_at TEXT NOT NULL
);
```

### `intel_source_state`

```sql
CREATE TABLE intel_source_state (
  source_id TEXT PRIMARY KEY REFERENCES intel_sources(id),
  last_attempt_at TEXT,
  last_success_at TEXT,
  next_due_at TEXT,
  last_error TEXT,
  consecutive_errors INTEGER NOT NULL DEFAULT 0,
  etag TEXT,
  last_modified TEXT,
  watermark TEXT,
  state_json TEXT NOT NULL DEFAULT '{}'
);
```

### `intel_crawl_runs`

```sql
CREATE TABLE intel_crawl_runs (
  id TEXT PRIMARY KEY,
  status TEXT NOT NULL,
  started_at TEXT NOT NULL,
  finished_at TEXT,
  source_count INTEGER NOT NULL DEFAULT 0,
  resource_count INTEGER NOT NULL DEFAULT 0,
  signal_count INTEGER NOT NULL DEFAULT 0,
  error TEXT,
  config_hash TEXT,
  summary_json TEXT NOT NULL DEFAULT '{}'
);
```

### `intel_resources`

```sql
CREATE TABLE intel_resources (
  id TEXT PRIMARY KEY,
  source_id TEXT NOT NULL REFERENCES intel_sources(id),
  run_id TEXT REFERENCES intel_crawl_runs(id),
  resource_type TEXT NOT NULL,
  url TEXT,
  canonical_url TEXT,
  final_url TEXT,
  platform TEXT,
  platform_id TEXT,
  status_code INTEGER,
  content_type TEXT,
  content_hash TEXT,
  title TEXT,
  description TEXT,
  published_at TEXT,
  fetched_at TEXT NOT NULL,
  raw_payload_json TEXT,
  extracted_text TEXT,
  metadata_json TEXT NOT NULL DEFAULT '{}',
  UNIQUE(source_id, platform, platform_id),
  UNIQUE(source_id, canonical_url, content_hash)
);
```

### `intel_media_assets`

```sql
CREATE TABLE intel_media_assets (
  id TEXT PRIMARY KEY,
  resource_id TEXT NOT NULL REFERENCES intel_resources(id),
  asset_type TEXT NOT NULL,
  url TEXT,
  platform TEXT,
  platform_id TEXT,
  title TEXT,
  duration_ms INTEGER,
  width INTEGER,
  height INTEGER,
  thumbnail_url TEXT,
  content_hash TEXT,
  phash TEXT,
  local_path TEXT,
  metadata_json TEXT NOT NULL DEFAULT '{}'
);
```

### `intel_signals`

```sql
CREATE TABLE intel_signals (
  id TEXT PRIMARY KEY,
  brand_name TEXT NOT NULL,
  signal_type TEXT NOT NULL,
  status TEXT NOT NULL,
  confidence REAL NOT NULL,
  title TEXT NOT NULL,
  summary TEXT,
  campaign_name TEXT,
  products_json TEXT NOT NULL DEFAULT '[]',
  first_seen_at TEXT NOT NULL,
  source_published_at TEXT,
  last_seen_at TEXT NOT NULL,
  score_breakdown_json TEXT NOT NULL DEFAULT '{}',
  created_at TEXT NOT NULL,
  updated_at TEXT NOT NULL
);
```

### `intel_signal_evidence`

```sql
CREATE TABLE intel_signal_evidence (
  id TEXT PRIMARY KEY,
  signal_id TEXT NOT NULL REFERENCES intel_signals(id),
  resource_id TEXT REFERENCES intel_resources(id),
  source_id TEXT REFERENCES intel_sources(id),
  evidence_type TEXT NOT NULL,
  url TEXT,
  text TEXT,
  published_at TEXT,
  confidence REAL,
  metadata_json TEXT NOT NULL DEFAULT '{}'
);
```

### `intel_signal_matches`

```sql
CREATE TABLE intel_signal_matches (
  id TEXT PRIMARY KEY,
  signal_id TEXT NOT NULL REFERENCES intel_signals(id),
  target_type TEXT NOT NULL,
  target_id TEXT NOT NULL,
  match_score REAL NOT NULL,
  reasons_json TEXT NOT NULL DEFAULT '[]',
  created_at TEXT NOT NULL,
  UNIQUE(signal_id, target_type, target_id)
);
```

### `intel_review_events`

```sql
CREATE TABLE intel_review_events (
  id TEXT PRIMARY KEY,
  signal_id TEXT NOT NULL REFERENCES intel_signals(id),
  action TEXT NOT NULL,
  note TEXT,
  created_at TEXT NOT NULL,
  actor TEXT
);
```

## 13. Proposed Pydantic Models

Core models should be strict and serializable.

```python
class IntelSource(BaseModel):
    id: str
    brand_name: str
    source_type: Literal[
        "youtube_channel",
        "rss",
        "sitemap",
        "pressroom",
        "official_webpage",
        "meta_ad_library",
        "tiktok_commercial_content",
        "internet_archive",
        "trade_press",
        "search_provider",
    ]
    tier: Literal["A", "B", "C", "D"]
    url: str | None = None
    platform: str | None = None
    platform_id: str | None = None
    enabled: bool = True
```

```python
class IntelResource(BaseModel):
    id: str
    source_id: str
    resource_type: str
    url: str | None
    canonical_url: str | None
    platform: str | None
    platform_id: str | None
    title: str | None
    description: str | None
    published_at: datetime | None
    fetched_at: datetime
    metadata: dict[str, Any]
```

```python
class IntelSignal(BaseModel):
    id: str
    brand_name: str
    signal_type: Literal[
        "new_ad_upload",
        "campaign_launch",
        "new_campaign_variant",
        "offer_change",
        "product_push",
        "creative_reuse",
        "ad_library_seen",
        "official_press_mention",
    ]
    status: Literal[
        "candidate",
        "corroborated",
        "matched_local",
        "accepted",
        "dismissed",
        "stale",
    ]
    confidence: float
    title: str
    summary: str | None
    campaign_name: str | None
    products: list[str]
    evidence: list[IntelEvidence]
```

## 14. Local-First and Testability Requirements

The crawler must be testable without:

- internet access
- API keys
- paid services
- GPU
- LM Studio
- browser automation

Every adapter should have:

- a protocol/interface
- a fake implementation
- fixture-backed tests
- deterministic sample payloads

Recommended test layout:

```text
tests/intelligence_crawler/
  test_config.py
  test_schema.py
  test_repository.py
  test_source_registry.py
  test_youtube_adapter.py
  test_rss_adapter.py
  test_sitemap_adapter.py
  test_metadata_extraction.py
  test_signal_generation.py
  test_confidence_scoring.py
  test_signal_dedup.py
  test_local_matching.py
  test_readonly_integration.py
  test_cli.py
  fixtures/
    youtube_playlist_items.json
    youtube_video_details.json
    toyota_pressroom_feed.xml
    toyota_pressroom_article.html
    sitemap.xml
```

## 15. API Surface

Add routes under:

```text
/api/intelligence
```

Suggested endpoints:

```text
GET  /api/intelligence/sources
POST /api/intelligence/sources
PATCH /api/intelligence/sources/{source_id}

POST /api/intelligence/crawl-runs
GET  /api/intelligence/crawl-runs
GET  /api/intelligence/crawl-runs/{run_id}

GET  /api/intelligence/signals
GET  /api/intelligence/signals/{signal_id}
POST /api/intelligence/signals/{signal_id}/accept
POST /api/intelligence/signals/{signal_id}/dismiss
POST /api/intelligence/signals/{signal_id}/rematch

GET  /api/intelligence/brands/{brand}/signals
GET  /api/intelligence/campaigns/{campaign_id}/signals
GET  /api/intelligence/ads/{ad_id}/signals
```

The API should expose provenance and score breakdowns so an analyst can understand why a signal exists.

## 16. CLI Surface

Suggested CLI commands:

```text
ad-classifier intel init-db
ad-classifier intel sources list
ad-classifier intel sources validate
ad-classifier intel crawl --source toyota_youtube
ad-classifier intel crawl --brand Toyota
ad-classifier intel crawl --due
ad-classifier intel signals list --brand Toyota
ad-classifier intel signals explain sig_x
ad-classifier intel signals match sig_x
```

R.1 should include only:

- `init-db`
- `crawl`
- `signals list`
- `signals explain`

More commands can wait until the data model stabilizes.

## 17. Agent Tool Surface

The NL agent should get read-only tools, not raw SQL first.

Suggested tools:

```text
list_intel_signals
get_intel_signal
explain_intel_signal
list_brand_intel
list_campaign_intel
match_intel_signal
```

Example agent use:

User asks:

```text
Has Toyota released any new ads recently?
```

Tool sequence:

1. `list_intel_signals(brand="Toyota", since="30d", statuses=["corroborated", "matched_local"])`
2. `get_intel_signal(signal_id="...")`
3. Answer with source URLs, dates, signal confidence, and match status.

The agent must never claim a campaign exists unless the signal evidence supports it.

## 18. Campaign Research Integration

Current campaign research has an `include_web` request field but web research is disabled. The recommended behavior:

1. `include_web=false`
   - current local-only behavior remains unchanged.

2. `include_web=true`
   - do not crawl live.
   - read stored intelligence signals related to the campaign brand/products/campaign phrases.
   - include those signals in the campaign research payload as `web_intelligence`.
   - clearly label freshness and source coverage.

Example response addition:

```json
{
  "web_available": true,
  "include_web": true,
  "web_intelligence": {
    "signals": [
      {
        "signal_id": "sig_toyota_2026_001",
        "type": "new_ad_upload",
        "confidence": 0.87,
        "title": "Official Toyota upload suggests new campaign creative",
        "evidence_urls": ["https://www.youtube.com/watch?v=..."]
      }
    ],
    "limits": "Signals come from the local intelligence crawler cache; no live web crawl was performed during this request."
  }
}
```

## 19. Frontend Integration Later

The first implementation can be backend/CLI only. Later, add a review page:

```text
/intelligence
```

Useful UI views:

- signal inbox
- brand watchlist
- source health
- signal detail with evidence
- local match suggestions
- accept/dismiss actions
- source configuration

The UI should make provenance visible. Each signal should show:

- source tier
- source URLs
- extracted date
- confidence breakdown
- local matches
- why it was grouped/deduped
- limitations

## 20. Source Registry Seeding

Initial source registry should be manually curated for a small number of brands. Do not try to monitor the entire internet initially.

Suggested initial brands:

- Toyota
- Ford
- Jeep
- T-Mobile
- Apple
- McDonald's
- Progressive
- Geico

For each brand, seed:

- official website domain
- official YouTube channel ID
- official pressroom/newsroom URL
- official RSS feed if available
- official sitemap URL
- optional known campaign landing-page domain/path

Source bootstrapping should be a manual review workflow:

1. candidate source discovered
2. analyst verifies it is official/relevant
3. source added to registry
4. crawler begins polling

## 21. Toyota Example Flow

Goal:

```text
Detect that Toyota released a new campaign or digital version of a TV ad.
```

Flow:

1. `toyota_youtube` source is due.
2. YouTube adapter polls official Toyota uploads playlist.
3. New video is found.
4. Metadata extractor reads title, description, published date, thumbnail, duration.
5. Signal generator sees ad-like terms or campaign/product language.
6. `toyota_pressroom` source is due.
7. RSS/sitemap adapter finds recent Toyota pressroom article with matching phrase.
8. Corroboration groups the YouTube upload and pressroom article into one signal.
9. Local matcher checks existing ads/campaigns for Toyota, phrase overlap, product names, and embeddings.
10. Signal is persisted as `corroborated` or `matched_local`.

Example stored signal:

```json
{
  "brand_name": "Toyota",
  "signal_type": "campaign_launch",
  "status": "corroborated",
  "confidence": 0.86,
  "campaign_name": "extracted or inferred phrase",
  "products": ["Camry"],
  "title": "Toyota official sources indicate new campaign creative",
  "evidence": [
    {
      "source": "toyota_youtube",
      "url": "https://www.youtube.com/watch?v=...",
      "evidence_type": "official_video_upload",
      "text": "Video title/description snippet..."
    },
    {
      "source": "toyota_pressroom",
      "url": "https://...",
      "evidence_type": "official_press_mention",
      "text": "Pressroom snippet..."
    }
  ],
  "score_breakdown": {
    "source_reliability": 0.42,
    "brand_identity": 0.15,
    "ad_likeness": 0.12,
    "campaign_phrase": 0.08,
    "corroboration": 0.09
  }
}
```

## 22. Media Handling

The crawler should treat media carefully.

Preferred order:

1. Store public platform IDs and URLs.
2. Store thumbnails if terms allow and if needed.
3. Store metadata and hashes.
4. Only download full video when explicitly configured and legally/operationally acceptable.
5. If video is downloaded, pass it through the existing ingest pipeline as a normal input, preserving source provenance.

Media matching options:

- thumbnail pHash
- optional sampled-frame pHash
- optional OCR from thumbnail/frame if allowed
- text embedding of title/description/press copy
- visual embedding of downloaded frames if allowed

## 23. Security and Safety

The crawler should:

- enforce request timeouts
- cap response body sizes
- restrict browser fallback to allowed domains
- avoid file path traversal in cached resources
- never execute downloaded scripts
- not follow arbitrary user-submitted URLs without validation
- not expose raw tracebacks through API
- log structured errors
- store secrets only through environment variables
- never write to submitted demo DB except through explicit accepted workflows, if later approved

## 24. Legal, Robots, and Platform Policy

Default rules:

1. Respect robots.txt for HTTP crawling.
2. Prefer APIs and feeds over HTML crawling.
3. Do not bypass login, paywall, bot checks, or technical restrictions.
4. Do not use unofficial scraping for platforms when official APIs exist and terms matter.
5. Store provenance and source limitations.
6. Keep optional platform adapters disabled unless credentials and access are configured.
7. Store source policy notes in the source registry.

Useful reference points for reviewers:

- Robots Exclusion Protocol RFC 9309: https://datatracker.ietf.org/doc/html/rfc9309
- YouTube Data API `channels.list`: https://developers.google.com/youtube/v3/docs/channels/list
- YouTube Data API `playlistItems.list`: https://developers.google.com/youtube/v3/docs/playlistItems/list
- YouTube API quota costs: https://developers.google.com/youtube/v3/determine_quota_cost
- Google sitemap/RSS/mRSS guidance: https://developers.google.com/search/docs/crawling-indexing/sitemaps/build-sitemap
- Meta Ad Library API: https://www.facebook.com/ads/library/api/
- TikTok Commercial Content API: https://developers.tiktok.com/products/commercial-content-api
- Internet Archive metadata API: https://archive.org/developers/metadata.html

## 25. Implementation Phases

### Phase 0: Design Review

Deliverables:

- this plan reviewed by other models
- final architecture decision
- source policy decision
- source registry shape
- DB schema draft
- no code changes beyond planning docs

Questions:

- Should the package be named `intelligence_crawler`, `ad_intel`, or `web_intelligence`?
- Should the database be `intelligence_crawler.db` or part of `entity_graph.db`?
- Which sources are allowed by default?
- Should any media downloads be allowed in v1?

### Phase 1: Skeleton and Persistence

Deliverables:

- package skeleton
- config loader
- SQLite schema
- repository
- source registry
- fake adapter
- CLI `init-db`
- tests for schema/repository/config

No internet required.

### Phase 2: YouTube Official Channel Adapter

Deliverables:

- YouTube adapter interface
- fixture-backed tests
- optional real API implementation behind `YOUTUBE_API_KEY`
- source state tracking
- playlist polling
- resource persistence
- basic `new_ad_upload` signal generation

Acceptance criteria:

- With fixture payloads, new official videos become resources.
- Ad-like videos become candidate signals.
- Duplicate polling does not duplicate resources/signals.
- No API key is needed for tests.

### Phase 3: RSS/Sitemap/Pressroom Adapter

Deliverables:

- RSS/Atom parser
- sitemap parser
- article metadata extractor
- OpenGraph/JSON-LD extraction
- pressroom signal generation
- official-source corroboration

Acceptance criteria:

- Fixture RSS/sitemap input produces resources.
- Matching pressroom + YouTube phrase creates a corroborated signal.
- Incremental polling works with GUID/URL/content hash.

### Phase 4: Dedup and Scoring

Deliverables:

- canonical URL dedup
- platform ID dedup
- signal merge logic
- confidence scoring
- score breakdowns
- tests for conflicting/duplicate sources

Acceptance criteria:

- Multiple evidence records can support one signal.
- Confidence is explainable.
- General search cannot create high-confidence signals by itself.

### Phase 5: Local Matching

Deliverables:

- brand/product matching against submitted DB and entity graph
- campaign phrase matching
- optional embedding matching using existing stores
- `intel_signal_matches`
- tests with seeded local ads/campaigns

Acceptance criteria:

- Signals can link to existing local ads/campaigns.
- Submitted DB is accessed read-only.
- No submitted records are mutated.

### Phase 6: API and Agent Tools

Deliverables:

- read APIs
- signal review endpoints
- read-only agent tools
- API tests
- agent tool tests

Acceptance criteria:

- User can list/explain signals.
- Agent can answer brand/campaign intelligence questions with citations.
- Review actions update only intelligence crawler tables.

### Phase 7: Campaign Research Integration

Deliverables:

- `include_web=true` reads stored signals
- campaign deep research includes `web_intelligence`
- tests for `include_web=false` compatibility
- tests for `include_web=true` with seeded signals

Acceptance criteria:

- Existing local-only research behavior is unchanged.
- Web intelligence is clearly labeled as cached crawler evidence.
- No live crawl happens inside campaign research.

### Phase 8: Optional Platform Ad Libraries

Deliverables:

- disabled-by-default adapter skeletons
- Meta adapter if access is available
- TikTok adapter if access is available
- coverage limitations in evidence payload

Acceptance criteria:

- Ad-library facts are stored with platform/source limitations.
- Ad-library signals can corroborate official-source signals.

### Phase 9: Frontend Review UI

Deliverables:

- signal inbox
- signal detail
- source health
- accept/dismiss
- local matches

Acceptance criteria:

- Analyst can inspect evidence before accepting signals.
- Confidence breakdown and source URLs are visible.

## 26. Recommended First Milestone

The smallest useful v1:

1. New `intelligence_crawler.db`.
2. Source registry with 2-3 manually configured brands.
3. YouTube official channel adapter.
4. RSS/sitemap pressroom adapter.
5. Candidate/corroborated signal persistence.
6. CLI listing and explanation.
7. No frontend.
8. No platform ad libraries.
9. No broad search.
10. No automatic media download.

This would already answer:

```text
What new official brand ad videos or campaign mentions have appeared recently?
```

## 27. Risks and Mitigations

| Risk | Mitigation |
|---|---|
| Source APIs change | Adapter interfaces, fixture tests, source health table |
| Search results are noisy | Use search only for discovery/source bootstrapping |
| Official channels post non-ad content | Ad-likeness scoring and candidate status |
| Campaign names are ambiguous | Require provenance and phrase corroboration |
| Media download rights are unclear | Store URLs/metadata first; downloads disabled by default |
| Crawler becomes too broad | Source registry and shallow crawling only |
| Signals pollute submitted DB | Separate DB and explicit accepted workflows |
| Live campaign research becomes slow | Campaign research reads cached signals only |
| LLM invents facts | Deterministic extraction first; LLM output must cite evidence |
| Duplicate signals multiply | Resource and signal dedup layers |

## 28. Questions for Other Models

Ask other models to critique these specific points:

1. Is a separate `intelligence_crawler.db` the right boundary, or should this live in `entity_graph.db`?
2. Is `ad_classifier/intelligence_crawler/` the right module name?
3. Are the source tiers sufficient for reliable campaign/ad discovery?
4. Should YouTube official-channel polling be the first adapter?
5. Should RSS/sitemap pressroom crawling be second?
6. Should any broad search adapter exist in v1, or should it wait?
7. Is the proposed signal confidence model too complex for v1?
8. What tables are missing from the proposed schema?
9. What should be the exact difference between `candidate`, `corroborated`, `matched_local`, and `accepted`?
10. Should campaign research use only accepted/corroborated signals, or include candidates with labels?
11. Should media downloads be disabled in v1?
12. How should the crawler handle local dealer ads versus national brand ads?
13. How should source registry bootstrapping work without unreliable search scraping?
14. What are the biggest legal/platform-policy risks?
15. What is the smallest demo that proves the crawler is useful?

## 29. Suggested Reviewer Prompt

Use this prompt with other models:

```text
You are reviewing a proposed v2 intelligence crawler for a local-first multimodal ad-classification system.

The crawler's purpose is to discover public internet signals about digital versions of TV ads and campaign launches, such as "Toyota released a new campaign/ad", and then persist source-grounded candidate signals locally. It should not mutate submitted ad records directly, should not become a broad scraper, and should prefer official brand/video/pressroom sources.

Please critique the architecture in intellegence_crawler.md. Focus on reliability, source strategy, data model, deduplication, confidence scoring, local-first operation, legal/platform-policy risks, and implementation phasing.

Return:
1. strongest parts of the plan
2. weakest assumptions
3. missing components
4. recommended schema changes
5. recommended source/adapter changes
6. a revised minimal v1 milestone
7. any red flags that should block implementation
```

## 30. Bottom Line

The correct v2 direction is not "crawl the internet for ads." It is:

```text
Maintain a trusted source registry, poll official structured sources incrementally, extract source-grounded ad/campaign signals, corroborate them, deduplicate them, match them to local ads/campaigns/entities, and expose them through cached local intelligence tools.
```

That gives reliable answers like "Toyota appears to have released a new campaign/ad" without turning the system into a brittle, noisy, or policy-risky web scraper.
