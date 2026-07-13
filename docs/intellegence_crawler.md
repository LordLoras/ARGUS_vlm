# Intelligence Crawler — Current State

> Last updated 2026-07-13.
> Companion docs: [overview](intellegence_crawler_overview.md),
> [normalized schema](intelligence_crawler_normalized_ad_schema.md),
> [operations and failure semantics](intelligence_crawler_operations.md),
> [demo/service brief](demo_present.md), and [follow-ups](intel_crawler_followups.md).

## What It Is

The intelligence crawler is the local-first digital-ad collection layer for ARGUS.
It watches curated US brands, polls adapter-backed ad sources, stores every observed
creative with provider-derived metadata and artifacts, and exposes a clean API/Watcher UI
for review.

It is separate from the submitted-ad classification pipeline. The crawler discovers
and catalogs digital ads. OCR, transcript extraction, multimodal classification, and
TV-campaign matching are explicitly outside this service and can be added by another
consumer later.

## Locked Decisions

| Area | Decision |
|---|---|
| Module | `ad_classifier/intelligence_crawler/` |
| Store | Own `intelligence_crawler.db` in WAL mode |
| Config | `intelligence_crawler.yaml` is a seed; DB rows are the source of truth after startup |
| Market | US-focused by default |
| Current data | `intel_resources` is the authoritative latest projection returned to normal API consumers |
| History | `intel_resource_observations` and `intel_source_runs` are append-only audit/diagnostic ledgers in the same DB, so current + history commit atomically |
| Provider data | Preserve the adapter's provider-derived snapshot in `metadata_json`; do not claim byte-for-byte raw response retention |
| API contract | Generate `resource.normalized` at read time from DB columns + metadata |
| Artifacts | Store screenshots/URLs/posters/links; do not auto-download full videos |
| Cold start | First poll records backfill and emits no live signals |
| Region model | `collection.requested_region_code` stores the US query context; `delivery.regions` is only for provider delivery stats |

## Built Components

Core:
- `config.py` — `IntelConfig`, path resolution, source seed config.
- `models.py` — strict Pydantic models for sources, resources, artifacts, runs, signals, and normalized resources.
- `schema.py` — SQLite DDL for `intel_sources`, `intel_resources`, media assets, runs, signals, and evidence.
- `repository.py` plus focused repository mixins — source state, latest resources, observations/runs, signals, and row projection.
- `normalized.py` — cross-provider resource normalizer for Google, Meta, and future adapters.
- `runner.py` + `run_policy.py` — source orchestration, atomic leasing, cold-start/backfill detection, scheduling, retry/cooldown, and idempotent refresh.
- `request_guard.py` — freshness guard and provider-wide rate-limit/block circuit breaker.
- `google_crawl_state.py` + `google_creatives.py` — durable Google cursors, incremental/full reconciliation planning, creative signatures, and preview reuse.
- `diagnostics.py` — stable failure categories/codes for UI changes, response changes, 429s, blocking, transport, parse, request-limit, asset, and configuration failures.
- `manager.py` — API-facing facade and source adapter factory.
- `worker_service.py` + `scheduler_service.py` — independent queue executor and
  due-source scheduler with durable leases and service heartbeats.
- `exports.py` + `contract.py` — versioned JSON/JSONL exports, opaque cursors, semantic
  change hashes, and atomic latest/status/health snapshots.
- `watchlist.py`, `detect.py`, `dedup.py`, `scoring.py`, `digest.py` — watchlist, newness detection, grouping, confidence, digest.

Adapters:
- `google_atc` — Google Ads Transparency Center via internal JSON-RPC, US region code `2840`, advertiser id (`AR...`) required.
- `meta_ad_library_ui` — public Meta Ad Library Playwright probe by verified Page ID, captures visible cards, screenshots, copy, media URLs, and version counts.
- `youtube_channel` — feed-first official-channel monitoring with optional Data API duration enrichment.
- `rss` — RSS/Atom newsroom and press-feed monitoring.
- `mock` — offline tests and local smoke checks.

Surfaces:
- CLI: `python -m ad_classifier intel init-db|worker|scheduler|export|source-types|watchlist|crawl|signals|digest|resolve|meta-probe`.
- API: versioned latest-resource cursor pages, semantic change feed, JSON/JSONL export,
  aggregate health, resource history, source/run diagnostics, retry, and durable queue
  endpoints under `/api/intelligence`.
- Frontend: Watcher at `/experimental/watcher`, a shell over the API that queues work,
  polls run state, and displays worker/scheduler/provider health.

## Data Shape

Each API resource includes both:

- `metadata`: latest adapter/provider-derived snapshot for debugging and provider mapping.
- `normalized`: stable cross-provider JSON for consumers.

Use `normalized` for application code and analysis. Use `metadata` only when debugging
or adding a provider mapper. See
[intelligence_crawler_normalized_ad_schema.md](intelligence_crawler_normalized_ad_schema.md)
for every field.

Important current behavior:
- `GET /resources` and `GET /resources/{id}` return only the latest projection.
- `GET /resources/changes` emits only semantic content changes and embeds the latest row.
- `GET /resources/export` and worker snapshots provide contract-versioned JSON for
  non-ARGUS consumers.
- Historical observations are opt-in through `GET /resources/{id}/history`.
- `first_seen_at` is immutable; `last_seen_at`/`fetched_at` advance when the item is observed again.
- `normalized` is computed at read time, not duplicated as a DB column.
- Google `region=US` and Meta `country=US` populate `collection.requested_region_code`.
- `delivery.regions` stays empty unless the provider returns actual delivery/impression stats.
- Default variants are synthesized from row text + artifacts when the provider does not expose explicit variant rows.

## Current Demo State

The 2026-07-13 ten-brand exercise left **10,500 latest resources** in the local DB:
9 Google McDonald's creatives, 9,217 Google Samsung creatives, and 1,274 Meta creatives
across Apple, DoorDash, Duolingo, GEICO, McDonald's, Samsung, and Starbucks. Sources were
returned to their pre-run disabled state after collection. The run ledger preserves the
complete/partial/429 outcomes. See [demo_present.md](demo_present.md) before any live refresh.

## Reliability Notes

- Canonical reliability tiers are Meta **A**, Google Ads Transparency **B**, and YouTube/RSS/newsroom/indirect sources **C**. Tier affects provenance/confidence, never health reporting.
- Poll outcomes are explicit: `success`, `not_modified`, `explicit_empty`, `partial`, or `failed`.
- Only a complete outcome advances `last_success_at` or activates a first baseline.
- Partial results may update resources actually observed, but retain the previous complete-success timestamp and schedule an earlier retry.
- Unique run owners plus atomic compare-and-set leases prevent overlapping source runs.
- FastAPI only queues long work. A separate worker claims and renews run leases; a
  separate scheduler inserts deduplicated due runs. Expired worker runs are failed and
  safely replaced, retaining provider cursors.
- `due=true` honors `next_due_at` and `cooldown_until`; 429 and provider failures use category-aware backoff.
- Normal explicit retries also honor freshness/cooldown; `force=true` is an operator-only override.
- HTTP `Retry-After` extends cooldown, and a rate-limit/block opens a provider-wide circuit so subsequent same-provider sources make zero requests.
- Full tracebacks stay in structured logs. API/UI receive bounded diagnostic code, category, phase, HTTP status, and safe message.
- Meta captures cards cumulatively while scrolling so virtualized cards are not lost, and reports configured collection limits as partial.
- Google checkpoints every successful page, resumes from that cursor after failure, performs low-request signature overlap scans between 72-hour full reconciliations, and reuses unchanged preview artifacts.

## Deliberate Non-goals

- Local downloads of remote videos as durable media assets.
- OCR/transcript/classification for crawler-collected ads.
- Mapping digital resources to TV ads/campaigns.
- Expanded Meta variant capture behind "See summary details".

Long crawls can be submitted through `POST /api/intelligence/crawl/queue`; they remain
queued until `intel worker` claims them. `intel scheduler` is an optional independent
process and is never started automatically by ARGUS.

## Verify

```powershell
python -m pytest tests/intelligence_crawler -q
ruff check ad_classifier/intelligence_crawler tests/intelligence_crawler
black --check ad_classifier/intelligence_crawler tests/intelligence_crawler
npm --prefix frontend run build
```

Current focused verification: **133 intelligence-crawler tests passed**.
