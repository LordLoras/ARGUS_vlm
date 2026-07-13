# Intelligence Crawler — Current Follow-ups

> Last updated 2026-07-13.

## Already Done

- Google ATC source for US advertiser creatives through internal JSON-RPC.
- Meta Ad Library public UI source through Playwright.
- DB-backed sources/resources/runs/signals/artifacts.
- Watcher UI resource/artifact browsing.
- Raw provider payload preservation in `metadata_json`.
- Cross-provider `resource.normalized` JSON generation.
- Latest-resource projection plus append-only observation/source-run ledgers.
- Explicit complete/partial/failed outcomes, stable failure categories, cooldown/backoff, and due scheduling.
- Queued crawl API for long-running provider work.
- Provider-wide circuit breaking, `Retry-After` handling, freshness guards, and explicit operator `force` override.
- Durable Google page checkpoints/resume, incremental overlap scans, periodic full reconciliation, and preview reuse.
- Independent durable worker and due-source scheduler services with heartbeats,
  abandoned-run recovery, and queue idempotency.
- Versioned cursor API, semantic resource change feed, streaming JSON/JSONL export, and
  atomic latest/status/health snapshots.
- Lean US region handling: `collection.requested_region_code`, not synthetic `delivery.regions`.
- Ten-brand exercise DB with 10,500 latest resources and complete per-source run diagnostics.

## Priority Backlog

### 1. Analyzer Handoff

Add an explicit handoff surface from crawler resource to downstream analysis.

Candidate shape:

- `crawler_analysis_jobs` table or queue.
- `resource_id`, provider, creative id, source URL.
- normalized assets and raw metadata snapshot.
- status fields: `queued`, `processing`, `completed`, `failed`.

This lets another local process or host request raw videos/images/screenshots for OCR,
transcript, VLM classification, and later campaign matching without coupling that logic
to the crawler.

### 2. Durable Media Policy

Decide what to download locally.

Recommended default:

- keep screenshots locally;
- keep provider image/video URLs in artifacts;
- download full videos only when a user queues analysis or pins a resource for demo;
- store copyright-sensitive assets for internal research only, not redistribution.

### 3. Google ATC Resilience and Telemetry

Google can 429 after repeated heavy requests.

Implemented: earlier successful pages survive later-page failures; continuation cursors
are committed per page; retry resumes; stale cursors fall back safely; 429/Retry-After,
provider circuits, incremental overlap scans, full reconciliation, preview reuse, and
Watcher health are all persisted. Remaining work is operational tuning from long-running
telemetry and optional alert delivery outside the API/UI.

### 4. Meta Variant Expansion

Current Meta cards preserve the visible variant count, but do not expand every hidden
variant behind Meta's details UI.

Follow-ups:

- inspect "See summary details" modal;
- capture per-version creative text/assets if exposed;
- keep screenshots as durable fallback when fbcdn media URLs expire.

### 5. Service Installation / Supervision

The worker and scheduler commands now exist and are deliberately opt-in. Later, choose
the production supervisor (Windows Service wrapper, Task Scheduler, or another local
process manager), log retention, restart policy, and external alert destination. ARGUS
should remain only their API/UI shell.

### 6. Digital Campaign Layer

After crawler resources are stable:

- cluster digital resources by brand/copy/assets;
- attach analyst-curated campaign names;
- optionally hand resources to a separate mapping service in a later project.

This remains separate from the current normalized JSON work.

## Non-goals For The Demo

- No OCR/transcript/VLM analysis of crawler resources.
- No automatic video downloading.
- No TV mapping.
- No broad live Google crawl during presentation.
