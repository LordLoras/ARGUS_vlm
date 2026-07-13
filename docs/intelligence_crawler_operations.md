# Intelligence Crawler API and Operations

> Last updated 2026-07-13. This document describes the middleware/service contract,
> crawl health semantics, and operator response to provider failures.

## Service Boundary

This service discovers and catalogs digital ads. Its durable contract is JSON over the
FastAPI surface plus files in the configured crawler cache. It does not perform OCR,
transcription, VLM classification, TV-ad matching, or automatic full-video downloads.

`intelligence_crawler.db` deliberately contains two kinds of data:

1. `intel_resources`: the authoritative latest projection used by normal consumers.
2. `intel_resource_observations`, `intel_source_runs`, and `intel_crawl_runs`: internal
   history/diagnostic ledgers.

They share one WAL-mode SQLite database—not two database files—so updating the latest
row and appending its observation can happen in one transaction. A separate database
would create a dual-write consistency problem. History is separated by table and API,
so consumers requesting resources still receive only current values.

## Resource API

| Endpoint | Purpose |
|---|---|
| `GET /api/intelligence/resources` | Paginated latest resources. Supports `brand`, `source_id`, `include_backfill`, `limit`, legacy `offset`, and opaque `cursor`; returns `schema_version`, `total`, `next_offset`, and `next_cursor`. |
| `GET /api/intelligence/resources/changes` | Semantic `created`/`updated` feed with `since` and opaque cursor. Every event embeds the current latest resource; routine freshness timestamps do not emit changes. |
| `GET /api/intelligence/resources/export?format=json\|jsonl` | Stream every filtered latest resource as versioned JSON or JSON Lines. |
| `GET /api/intelligence/resources/{resource_id}` | One latest resource. |
| `GET /api/intelligence/resources/{resource_id}/history` | Append-only observations for diagnostics/replay. Not part of the normal latest-data feed. |
| `GET /api/intelligence/resources/{resource_id}/screenshot` | A cache-confined local card screenshot, when present. |

`first_seen_at` never changes. `last_seen_at` and `fetched_at` describe the latest
successful observation of that resource. Media assets are projected into
`intel_media_assets` while the adapter metadata snapshot remains available in
`metadata`.

The current contract version is `1.0`. Cursor pagination is preferred for middleware
because rows added during a long export cannot shift later pages. Offset pagination is
retained for the existing ARGUS shell. The change feed is intentionally not the raw
observation ledger: it records a change only when stable provider content differs.

## Crawl API

| Endpoint | Behavior |
|---|---|
| `POST /api/intelligence/crawl` | Synchronous bounded crawl; useful for CLI/demo actions. |
| `POST /api/intelligence/crawl/queue` | Durably inserts a queued row and returns HTTP 202 with a `run_id`. It never calls a provider in the API process. |
| `POST /api/intelligence/sources/{source_id}/crawl` | Synchronous explicit-source crawl, even when disabled; honors freshness/cooldown by default. |
| `POST /api/intelligence/sources/{source_id}/crawl/queue` | Queued explicit-source crawl. |
| `GET /api/intelligence/runs` | Recent crawl summaries. |
| `GET /api/intelligence/runs/{run_id}` | Crawl plus every per-source outcome/diagnostic. |
| `POST /api/intelligence/runs/{run_id}/retry` | Queue the same terminal run request again; source-level cooldown/circuit/cursor state still applies. |
| `GET /api/intelligence/health` | Aggregate queue, worker, scheduler, source, circuit, and resume health for UI/monitoring. |
| `GET /api/intelligence/source-statuses` | Latest health for all/non-filtered sources in one request. |
| `GET /api/intelligence/sources/{source_id}/status` | Source state plus recent runs. |

Queued execution belongs to an independent worker. The API, worker, and scheduler may be
three processes using the same WAL-mode database:

```powershell
# Terminal/process 1: API + ARGUS consumer surface
python -m ad_classifier api

# Terminal/process 2: claim durable queued runs and call providers
python -m ad_classifier intel worker

# Terminal/process 3: periodically enqueue one due-source run
python -m ad_classifier intel scheduler
```

Use `--once` on either service for Task Scheduler, tests, or supervised one-shot runs.
These commands are opt-in: this repository does not install them as Windows services or
start them at login. The scheduler never contacts a provider; it only checks due state
and inserts a deduplicated queue row. The worker is the only queued-run executor.

Queue POSTs accept an optional `Idempotency-Key` header (maximum 200 characters). Reusing
the key returns the original run, preventing double-clicks or client retries from
creating duplicate provider work.

All crawl payloads accept `force: false`. Keep the default for routine and UI-driven
runs. `force: true` bypasses freshness, source cooldown, and provider-circuit guards and
is intended only for deliberate operator recovery/testing; leases are never bypassed.

## Poll Outcomes

| Outcome | Complete? | Advances `last_success_at`? | Meaning |
|---|---:|---:|---|
| `success` | yes | yes | Provider result was parsed and collection ended normally. |
| `not_modified` | yes | yes | Conditional request reported no changes. |
| `explicit_empty` | yes | yes | Provider explicitly showed/returned a valid empty result. |
| `partial` | no | no | Some useful items were retained, but pagination, enrichment, or extraction was incomplete. |
| `failed` | no | no | No trustworthy provider inventory was produced. |

A first poll activates its baseline only when the outcome is complete. This prevents a
truncated first crawl from causing unseen back-catalog items to look like newly launched
ads on the next run.

## Failure Categories

Every diagnostic has a stable `code`, broad `category`, safe `message`, provider,
phase, retryability, optional HTTP status, and bounded details. Full exception tracebacks
go only to structured logs.

| Category | Typical cause | Operator action |
|---|---|---|
| `provider_ui_changed` | Meta no longer exposes recognized cards/empty state | Inspect saved full-page screenshot and update public-UI selectors/contracts. |
| `provider_api_changed` | Google internal RPC response shape changed | Compare a current response with parser fixtures; update parser before retrying broadly. |
| `rate_limited` | HTTP 429/quota response | Wait for persisted cooldown; reduce page/preview budgets or poll frequency. |
| `request_limit` | Configured page/card/scroll cap ended collection | Raise the specific bounded limit or accept partial coverage; do not label the run complete. |
| `blocked` | 403, CAPTCHA, login, or checkpoint | Stop repeated retries; verify public access and collection policy. |
| `transport` | Timeout, DNS, connection, provider 5xx | Retry after backoff and check provider/network status. |
| `parse_error` | Malformed XML/JSON or unsupported feed root | Inspect response/content type; a login/error HTML page must not count as empty success. |
| `asset_fetch` | Preview/image/video enrichment failed | Inventory items remain current, but the run is partial and retries earlier. |
| `configuration` | Missing Page ID, advertiser ID, feed URL, or client | Correct source configuration; automatic retries use a long delay. |
| `authentication` | Invalid/expired optional API credentials | Rotate credentials; never include credential text in diagnostics. |

## Scheduling and Concurrency

- `due=true` selects enabled, unarchived sources whose `next_due_at` and
  `cooldown_until` are due.
- Explicit `source_id` runs bypass enabled selection but return a durable
  `source_not_due`, `source_cooldown_active`, or `provider_circuit_open` skipped result
  without network traffic when guarded. Use `force=true` only deliberately.
- Each crawl/source pair has a unique lease owner. Lease acquisition is one atomic
  compare-and-set update; a shared process name cannot re-enter a held lease.
- Successful complete polls use the source interval. Partial polls retry sooner.
  Rate limits and failures use category-aware bounded exponential backoff. A provider's
  `Retry-After` header is persisted and wins when it requests a longer wait.
- A rate-limit or access-block failure opens a provider-wide circuit until its persisted
  cooldown. Remaining sources of that provider are logged as skipped without making a
  request. Other provider families continue.
- Archiving a source disables it and preserves current resources and history. If it is
  archived during a poll, the provider result is discarded.
- A worker atomically claims one queued run with `BEGIN IMMEDIATE`, records its owner,
  and renews a run lease plus service heartbeat while the provider is active.
- If a worker disappears, the next worker marks the expired run failed and creates a
  fresh replacement run with `recovered_from`. Provider/source state—including a Google
  page cursor—survives, so the replacement resumes safely. Automatic abandoned-run
  recovery stops after `service.max_run_attempts`.
- Only one active scheduler-origin run may exist. Repeated scheduler ticks therefore do
  not pile up duplicate due crawls while a worker is busy.

## Reliability Tiers

The tier is canonical per adapter family and cannot drift through UI/config overrides:

- Tier A: Meta Ad Library (direct first-party ad library).
- Tier B: Google Ads Transparency (first-party transparency data through a brittle,
  unofficial internal RPC).
- Tier C: YouTube, RSS/newsroom, and other indirect or third-party discovery.

Tier affects confidence/provenance scoring. It never suppresses a failure, changes
whether a result is complete, or gates an ad.

Google pagination is bounded by `max_pages` when it is a positive integer. Set it to
`0`, `null`, or `"unlimited"` to follow continuation tokens until Google reports the end
of the result set or interrupts a request; the bundled Google sources use this uncapped
mode by default. A provider interruption stops all remaining requests for that source,
retains earlier pages as a partial result, and records the machine-readable failure
category and code in the run ledger.

Google additionally uses three request-minimization/recovery layers:

1. Every successful page durably stores the next opaque cursor and page number. A later
   retry uses `scan_mode=resume`; a rejected/expired cursor is cleared and retried once
   from page one.
2. Normal incremental scans start at the newest page and stop after three consecutive
   fully-known, signature-unchanged pages (`unchanged_pages_before_stop`). New or changed
   ads still flow to the current projection; verified unchanged rows advance
   `last_seen_at`/`fetched_at` without duplicating payload snapshots or refetching previews.
3. A periodic full reconciliation (`full_reconcile_hours`, default 72) scans to provider
   end so older changes or ordering anomalies are eventually observed. Checkpoints expire
   after `checkpoint_ttl_hours` (default 24), preventing a stale cursor from wedging a source.

Run rows expose `scan_mode`, `resumed`, `checkpoint_page`, and `stop_reason`; source status
exposes only `resume_available`/`resume_page`, never the opaque cursor itself. A preview
429/block stops the remaining preview burst immediately and opens the same circuit.

## Optional Mutation Authentication

Read endpoints remain available for local consumers. If the environment variable named
by `mutation_api_key_env` (default `INTELLIGENCE_CRAWLER_API_KEY`) is set, every crawler
POST/PATCH/DELETE route requires the same value in `X-Intelligence-Key`. Leave it unset
for a loopback-only desktop demo; set it when exposing the service beyond localhost.

## JSON Files For Non-HTTP Consumers

The worker atomically refreshes these files after every terminal run when
`service.write_snapshots_after_run` is true:

- `latest_resources.json` — authoritative latest resource array, contract version `1.0`;
- `source_statuses.json` — current provider/source diagnostic state;
- `health.json` — the same aggregate state as `/api/intelligence/health`.

Their directory is `service.snapshot_dir` (default
`./output/intelligence_crawler`). Temporary files are replaced only after a complete
write, so a consumer never reads a half-written JSON document. Generate an explicit
filtered export without running a provider:

```powershell
python -m ad_classifier intel export --output .\output\latest.json --format json
python -m ad_classifier intel export --output .\output\latest.jsonl --format jsonl --brand Samsung
```

## Health Checklist

1. Start with `/health`. `critical` means queued work cannot run or a run lease was
   abandoned; `degraded` means a source/provider/scheduler requires attention; `healthy`
   means no active issue. A missing service is informational until work depends on it.
2. Use `/source-statuses` for the exact provider cause and alert when `last_outcome` is
   `partial` or `failed`.
3. Alert on `last_success_at` age, not merely `last_attempt_at`.
4. Inspect `failure_category`, `error_code`, and `phase` before retrying.
5. Use `/runs/{run_id}` for request/page/provider-item counts and truncation details.
6. If `resume_available` is true, let cooldown expire and use normal Retry; the crawler
   continues from the saved Google page. Old failures recorded before migration 004 have
   no recoverable token and must restart from page one.
7. Inspect structured logs for the traceback; never expose them to API clients.
8. Treat `explicit_empty` as healthy only because the adapter recognized a provider
   empty state—an unrecognized blank page is `provider_ui_changed`/failed.
