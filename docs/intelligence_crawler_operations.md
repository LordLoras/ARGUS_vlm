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
| `GET /api/intelligence/resources` | Paginated latest resources. Supports `brand`, `source_id`, `include_backfill`, `limit`, and `offset`; returns `total` and `next_offset`. |
| `GET /api/intelligence/resources/{resource_id}` | One latest resource. |
| `GET /api/intelligence/resources/{resource_id}/history` | Append-only observations for diagnostics/replay. Not part of the normal latest-data feed. |
| `GET /api/intelligence/resources/{resource_id}/screenshot` | A cache-confined local card screenshot, when present. |

`first_seen_at` never changes. `last_seen_at` and `fetched_at` describe the latest
successful observation of that resource. Media assets are projected into
`intel_media_assets` while the adapter metadata snapshot remains available in
`metadata`.

## Crawl API

| Endpoint | Behavior |
|---|---|
| `POST /api/intelligence/crawl` | Synchronous bounded crawl; useful for CLI/demo actions. |
| `POST /api/intelligence/crawl/queue` | Returns HTTP 202 with a `run_id`; executes after the response. Preferred for middleware and long Meta crawls. |
| `POST /api/intelligence/sources/{source_id}/crawl` | Synchronous explicit-source crawl, even when disabled. |
| `POST /api/intelligence/sources/{source_id}/crawl/queue` | Queued explicit-source crawl. |
| `GET /api/intelligence/runs` | Recent crawl summaries. |
| `GET /api/intelligence/runs/{run_id}` | Crawl plus every per-source outcome/diagnostic. |
| `GET /api/intelligence/source-statuses` | Latest health for all/non-filtered sources in one request. |
| `GET /api/intelligence/sources/{source_id}/status` | Source state plus recent runs. |

Queued execution through FastAPI background tasks avoids holding a client connection,
but it is still in-process. For stronger crash recovery or multiple API replicas, run a
separate local scheduler/worker that claims queued rows; the current ledger schema is
already suitable for that evolution.

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
- Explicit `source_id` runs bypass enabled/due selection for diagnosis.
- Each crawl/source pair has a unique lease owner. Lease acquisition is one atomic
  compare-and-set update; a shared process name cannot re-enter a held lease.
- Successful complete polls use the source interval. Partial polls retry sooner.
  Rate limits and failures use category-aware bounded exponential backoff.
- Archiving a source disables it and preserves current resources and history. If it is
  archived during a poll, the provider result is discarded.

## Reliability Tiers

The tier is canonical per adapter family and cannot drift through UI/config overrides:

- Tier A: Meta Ad Library (direct first-party ad library).
- Tier B: Google Ads Transparency (first-party transparency data through a brittle,
  unofficial internal RPC).
- Tier C: YouTube, RSS/newsroom, and other indirect or third-party discovery.

Tier affects confidence/provenance scoring. It never suppresses a failure, changes
whether a result is complete, or gates an ad.

## Optional Mutation Authentication

Read endpoints remain available for local consumers. If the environment variable named
by `mutation_api_key_env` (default `INTELLIGENCE_CRAWLER_API_KEY`) is set, every crawler
POST/PATCH/DELETE route requires the same value in `X-Intelligence-Key`. Leave it unset
for a loopback-only desktop demo; set it when exposing the service beyond localhost.

## Health Checklist

1. Use `/source-statuses` for the dashboard and alert when `last_outcome` is `partial`
   or `failed`.
2. Alert on `last_success_at` age, not merely `last_attempt_at`.
3. Inspect `failure_category`, `error_code`, and `phase` before retrying.
4. Use `/runs/{run_id}` for request/page/provider-item counts and truncation details.
5. Inspect structured logs for the traceback; never expose them to API clients.
6. Treat `explicit_empty` as healthy only because the adapter recognized a provider
   empty state—an unrecognized blank page is `provider_ui_changed`/failed.
