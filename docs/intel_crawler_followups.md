# Intelligence Crawler — Current Follow-ups

> Last updated 2026-07-13.

## Already Done

- Google ATC source for US advertiser creatives through internal JSON-RPC.
- Meta Ad Library public UI source through Playwright.
- DB-backed sources/resources/runs/signals/artifacts.
- Watcher UI resource/artifact browsing.
- Raw provider payload preservation in `metadata_json`.
- Cross-provider `resource.normalized` JSON generation.
- Lean US region handling: `collection.requested_region_code`, not synthetic `delivery.regions`.
- One-brand demo DB: McDonald's with 9 Google ATC resources and 172 Meta resources.

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

### 3. Google ATC Resilience

Google can 429 after repeated heavy requests.

Follow-ups:

- lower default preview limits for broad demo sources;
- add per-provider cooldown state after 429;
- expose `last_error` and cooldown in Watcher source cards;
- keep McDonald's ATC as the safe live demo source.

### 4. Meta Variant Expansion

Current Meta cards preserve the visible variant count, but do not expand every hidden
variant behind Meta's details UI.

Follow-ups:

- inspect "See summary details" modal;
- capture per-version creative text/assets if exposed;
- keep screenshots as durable fallback when fbcdn media URLs expire.

### 5. Scheduler

Manual per-source runs are safest now. Later:

- honor `intel_source_state.next_due_at`;
- add a separate scheduled crawler process;
- keep it separate from the GPU-heavy worker.

### 6. Digital Campaign Layer

After crawler resources are stable:

- cluster digital resources by brand/copy/assets;
- attach analyst-curated campaign names;
- later compare to submitted/TV campaign clusters.

This remains separate from the current normalized JSON work.

## Non-goals For The Demo

- No OCR/transcript/VLM analysis of crawler resources.
- No automatic video downloading.
- No TV mapping.
- No broad live Google crawl during presentation.
