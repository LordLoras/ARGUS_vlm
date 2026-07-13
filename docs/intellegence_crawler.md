# Intelligence Crawler — Current State

> Last updated 2026-07-13.
> Companion docs: [overview](intellegence_crawler_overview.md),
> [normalized schema](intelligence_crawler_normalized_ad_schema.md),
> [demo runbook](DEMO_RUNBOOK.md), and [follow-ups](intel_crawler_followups.md).

## What It Is

The intelligence crawler is the local-first digital-ad collection layer for ARGUS.
It watches curated US brands, polls adapter-backed ad sources, stores every observed
creative with raw provider metadata and artifacts, and exposes a clean API/Watcher UI
for review.

It is separate from the submitted-ad classification pipeline. The crawler discovers
and catalogs digital ads; OCR, transcript extraction, multimodal classification, and
TV-campaign matching are still downstream responsibilities.

## Locked Decisions

| Area | Decision |
|---|---|
| Module | `ad_classifier/intelligence_crawler/` |
| Store | Own `intelligence_crawler.db` in WAL mode |
| Config | `intelligence_crawler.yaml` is a seed; DB rows are the source of truth after startup |
| Market | US-focused by default |
| Raw data | Preserve provider/adapter payloads in `intel_resources.metadata_json` |
| API contract | Generate `resource.normalized` at read time from DB columns + metadata |
| Artifacts | Store screenshots/URLs/posters/links; do not auto-download full videos |
| Cold start | First poll records backfill and emits no live signals |
| Region model | `collection.requested_region_code` stores the US query context; `delivery.regions` is only for provider delivery stats |

## Built Components

Core:
- `config.py` — `IntelConfig`, path resolution, source seed config.
- `models.py` — strict Pydantic models for sources, resources, artifacts, runs, signals, and normalized resources.
- `schema.py` — SQLite DDL for `intel_sources`, `intel_resources`, media assets, runs, signals, and evidence.
- `repository.py` — persistence, source CRUD, resource views, artifact summaries, normalized JSON generation.
- `normalized.py` — cross-provider resource normalizer for Google, Meta, and future adapters.
- `runner.py` — source orchestration, leasing, cold-start/backfill detection, idempotent refresh.
- `manager.py` — API-facing facade and source adapter factory.
- `watchlist.py`, `detect.py`, `dedup.py`, `scoring.py`, `digest.py` — watchlist, newness detection, grouping, confidence, digest.

Adapters:
- `google_atc` — Google Ads Transparency Center via internal JSON-RPC, US region code `2840`, advertiser id (`AR...`) required.
- `meta_ad_library_ui` — public Meta Ad Library Playwright probe by verified Page ID, captures visible cards, screenshots, copy, media URLs, and version counts.
- `youtube_channel` — feed-first official-channel monitoring with optional Data API duration enrichment.
- `rss` — RSS/Atom newsroom and press-feed monitoring.
- `mock` — offline tests and local smoke checks.

Surfaces:
- CLI: `python -m ad_classifier intel init-db|source-types|watchlist|crawl|signals|digest|resolve|meta-probe`.
- API: `/api/intelligence/sources`, `/resources`, `/signals`, `/digest`, `/watchlist`, `/source-types`, `/crawl`.
- Frontend: Watcher at `/experimental/watcher`, with source curation, per-source run buttons, resource cards, screenshots, media URLs, and artifact summaries.

## Data Shape

Each API resource includes both:

- `metadata`: raw adapter/provider payload preserved for replay/debugging.
- `normalized`: stable cross-provider JSON for consumers.

Use `normalized` for application code and analysis. Use `metadata` only when debugging
or adding a provider mapper. See
[intelligence_crawler_normalized_ad_schema.md](intelligence_crawler_normalized_ad_schema.md)
for every field.

Important current behavior:
- `normalized` is computed at read time, not duplicated as a DB column.
- Google `region=US` and Meta `country=US` populate `collection.requested_region_code`.
- `delivery.regions` stays empty unless the provider returns actual delivery/impression stats.
- Default variants are synthesized from row text + artifacts when the provider does not expose explicit variant rows.

## Current Demo State

The local demo DB was reset on 2026-07-13 and repopulated with one brand:

| Brand | Source | Resources |
|---|---|---:|
| McDonald's | Google Ads Transparency Center | 9 |
| McDonald's | Meta Ad Library | 172 |

Both McDonald's sources are enabled in the DB. Other seed sources remain available but have
zero resources until crawled again. See [DEMO_RUNBOOK.md](DEMO_RUNBOOK.md) for how to
demo or refresh this data without triggering broad Google 429 risk.

## Reliability Notes

- First poll is always baseline/backfill; live signals start only after activation.
- Re-polls update rows in place by stable external id.
- Source leases prevent overlapping runs.
- Per-source failures degrade the run instead of corrupting other sources.
- Google ATC can still 429 after heavy use. Keep demo crawls small; McDonald's ATC is the safe live source.
- Meta crawls are browser-driven and slower. Run them before a demo, not on stage.

## What Is Not Built Yet

- Media-analysis handoff queue from crawler resource to OCR/transcript/VLM processing.
- Local downloads of remote videos as durable media assets.
- OCR/transcript/classification for crawler-collected ads.
- Digital campaign clustering and mapping to TV campaigns.
- Expanded Meta variant capture behind "See summary details".
- A scheduler that honors `next_due_at`; today manual/source-specific runs are safest.
- Local matching from crawler signals to submitted ads/campaign records.

## Verify

```powershell
python -m pytest tests/intelligence_crawler -q
ruff check ad_classifier/intelligence_crawler tests/intelligence_crawler
black --check ad_classifier/intelligence_crawler tests/intelligence_crawler
npm --prefix frontend run build
```

Current crawler test count as of this update: **104 passing tests**.
