# ARGUS Digital Ad Crawler — Demo & Service Brief

> Last updated 2026-07-13.

## Service At A Glance

The intelligence crawler is ARGUS's local-first digital-ad collection middleware. It
collects the latest observable ads and creative metadata from curated brand/provider
sources, records exactly how every crawl ended, and serves normalized JSON to ARGUS or
another consumer. The Watcher frontend is a presentation and operations shell; provider
collection does not run inside React or a FastAPI background task.

The current reliability tiers are intentional:

- **Tier A — Meta Ad Library:** first-party ad library and the strongest current source.
- **Tier B — Google Ads Transparency:** first-party transparency inventory through a
  brittle, unofficial internal RPC.
- **Tier C — YouTube, newsroom/RSS, and third-party discovery:** useful corroborating or
  discovery sources, but not treated as authoritative ad-library coverage.

OCR, AI/VLM classification, full-video analysis, campaign clustering, and TV-ad mapping
are not responsibilities of this service. A downstream service can consume the crawler's
JSON and artifacts later without coupling those workloads to provider collection.

## Runtime Model

| Component | Responsibility | Provider requests? |
|---|---|---:|
| ARGUS Watcher | Show cached ads, source/run diagnostics, queue actions, and service health. | No |
| FastAPI | Serve latest JSON, changes, exports, health, and durably enqueue crawl runs. | Only for explicit synchronous developer endpoints |
| Crawler worker | Atomically claim queued runs, enforce leases/guards, call adapters, and write results/snapshots. | Yes |
| Scheduler | Find enabled sources that are due and enqueue one deduplicated due run. | No |
| `intelligence_crawler.db` | WAL-mode latest projection, queue, source state, observations, and diagnostic ledgers. | No |

The worker and scheduler are independent opt-in processes. They are not installed as
Windows services and are not started automatically. This keeps the current demo safe
while preserving a clean deployment boundary for later supervision.

The database contains two logical views in one atomic store:

- `intel_resources` is the authoritative latest projection returned to normal consumers.
- observations, resource changes, crawl runs, and source runs are secondary audit and
  recovery ledgers. Consumers do not need to replay them to obtain current JSON.

## Reliability And Recovery

- Routine runs honor freshness, `next_due_at`, cooldowns, and provider-wide circuits, so
  current cached copy does not cause unnecessary requests.
- Queue submissions support `Idempotency-Key`; worker claims and source leases prevent
  duplicate execution.
- Every failure exposes a stable cause such as `provider_ui_changed`,
  `provider_api_changed`, `rate_limited`, `request_limit`, `blocked`, `transport`, or
  `parse_error`. Full tracebacks remain in structured logs.
- Google persists a page cursor after every successful page. A safe retry resumes from
  that cursor; expired/rejected cursors fall back once to page one.
- An abandoned worker run is failed and replaced only after its source lease expires,
  preventing a stalled process and its replacement from flooding the provider.
- `GET /api/intelligence/health` reports queue, worker, scheduler, source, circuit, and
  resume state. `critical` means work cannot currently progress safely; `degraded` means
  a provider/source needs attention.

## Consumer Contract

The current contract version is `1.0`:

| Surface | Use |
|---|---|
| `GET /api/intelligence/resources` | Latest-only normalized resources with preferred opaque cursor pagination. |
| `GET /api/intelligence/resources/changes` | Semantic created/updated events; timestamp-only refreshes do not produce noise. |
| `GET /api/intelligence/resources/export?format=json\|jsonl` | Stream a filtered latest-only export. |
| `GET /api/intelligence/runs/{run_id}` | Run and per-source request/page/error diagnostics. |
| `POST /api/intelligence/runs/{run_id}/retry` | Queue the same request again while retaining cooldown/cursor guards. |
| `GET /api/intelligence/health` | Aggregate operational state for ARGUS or monitoring. |

After a worker run, atomic non-HTTP snapshots are written by default to
`output/intelligence_crawler/`:

- `latest_resources.json`
- `source_statuses.json`
- `health.json`

## Start / Access

- Start everything: `.\start.bat`
- Stop everything: `.\stop.bat`
- Local URL: `http://localhost:5173/experimental/watcher`
- Tunnel URL, if configured: `https://argus.rest/experimental/watcher`
- Demo login: `h-tech` / `argusdemo` from `frontend/.env.local`

If you only need the Watcher and not the worker:

```powershell
.\.venv\Scripts\python.exe -u -m ad_classifier api --host 127.0.0.1 --port 8000
npm --prefix frontend run dev -- --host 127.0.0.1 --port 5173
```

## Current Demo Dataset

The crawler DB contains the preserved 2026-07-13 ten-brand exercise. All sources were
returned to disabled after collection, so opening Watcher cannot trigger network traffic.

| Brand | Source | Resources | Notes |
|---|---|---:|---|
| Apple | Meta Ad Library | 130 | Complete visible-card run. |
| DoorDash | Meta Ad Library | 250 | Partial at the configured card limit. |
| Duolingo | Meta Ad Library | 49 | Complete visible-card run. |
| GEICO | Meta Ad Library | 250 | Partial at the configured card limit. |
| McDonald's | Google Ads Transparency Center | 9 | Small ATC set with video links/posters. |
| McDonald's | Meta Ad Library | 268 | Cross-provider comparison brand. |
| Samsung | Google Ads Transparency Center | 9,217 | Large preserved catalog for scale/pagination demo. |
| Samsung | Meta Ad Library | 77 | Complete visible-card run. |
| Starbucks | Meta Ad Library | 250 | Partial at the configured card limit. |

Watcher should show:

- `10` brands from the seed/watchlist.
- `0/17` enabled sources (safe cached demo state).
- `10,500` resources.
- Preserved run/source health showing complete, configured-limit partial, and real Google 429 causes.

Screenshots from before/after the reset live in:

```text
output/intel_demo_screenshots/
```

## What To Show

1. Open Watcher.
2. Select **McDonald's** for the clearest Google/Meta comparison, or **Samsung** to show scale.
3. Show the source cards and explain that disabled affects future polling, not preserved data.
4. Scroll to **Resources captured**.
5. Use adapter filter:
   - `All adapters`
   - `Google Ads Transparency`
   - `Meta Ad Library`
6. Use sort:
   - `Video first` to show richer cards.
   - `Most versions` to show Meta multi-version counts.
7. Open original provider links from cards:
   - `View on ATC`
   - `View in Ad Library`

## Live Run Guidance

The reliable presentation path is the cached DB. Do not start a broad provider crawl on
stage. A normal explicit retry is guarded: if the copy is fresh, cooling down, or another
source opened the provider circuit, it creates a skipped run with zero provider requests.

Operator retry after the displayed due/cooldown time:

```powershell
python -m ad_classifier intel crawl --source mcdonalds_atc
```

If a post-migration Google run was interrupted after at least one page, Watcher shows
`Retry / resume` plus the saved page. The normal retry continues from that cursor. The
real 429 runs already in this demo DB happened before migration 004, so they correctly
have no saved cursor and will restart from page one when eventually retried.

Avoid live during the demo:

```powershell
python -m ad_classifier intel crawl --source mcdonalds_meta_ads
```

Meta is browser-driven and can take minutes. Run it before the demo if you need to refresh.

Never use `--force` on stage. It intentionally bypasses freshness, cooldown, and provider
circuit guards and exists only for controlled operator recovery/testing.

Watcher run buttons now enqueue durable work and do not crawl inside FastAPI. Existing
resources render without either service. If the demo must execute a queued crawl, start
the worker in a separate terminal first:

```powershell
python -m ad_classifier intel worker
```

The scheduler is optional for the demo and should remain stopped unless demonstrating
automatic due polling. Watcher exposes both heartbeats and clearly reports queued work
when no worker is running.

## Back Up / Rebuild The Demo DB

Back up the crawler DB before experimenting:

```powershell
Copy-Item .\intelligence_crawler.db .\output\intelligence_crawler.demo-backup.db
```

Deleting/rebuilding the DB discards the 10,500-resource demo and can require hours of
provider work or hit 429. If a rebuild is truly needed, delete only the crawler DB (never
the submitted-ad DB), run `intel init-db`, enable sources intentionally, and use queued
normal crawls. Preserve cooldowns; do not force a multi-brand rebuild.

## Known Caveats

- The crawler stores raw metadata and normalized JSON; it does not OCR/classify these ads yet.
- Remote Meta media URLs can expire; local screenshots remain the durable visual fallback.
- Google ATC has no official US commercial API. The adapter uses the ATC internal RPC.
- Meta's official API does not return US commercial ads; the adapter reads the public UI.
- `delivery.regions` is normally empty in the US demo. The requested market is stored in
  `normalized.collection.requested_region_code`.
