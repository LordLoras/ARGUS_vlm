# ARGUS Suggestions and Roadmap

Last updated: 2026-05-17

This file tracks current product and implementation suggestions against the scope described in `getting_started.html` and `technical_detail.html`.

## Scope Guardrails

ARGUS remains a local-first ad intelligence system:

- Keep ingestion, OCR, transcript alignment, VLM classification, marketing entities, embeddings, search, campaigns, and the read-only agent as the core product.
- Keep the classification path categorization-only. Do not add approve, block, flag, escalation, or human-review workflows.
- Treat risk labels as descriptive observation tags for search and analysis.
- Keep the frontend decoupled from the backend through JSON endpoints and SSE.
- Keep optional creative-analysis reports downstream of persisted evidence so they do not block ingestion or classification.
- Keep research local-first. Internet research remains out of scope until a controlled web research layer exists.

## Recently Completed

These items were previously listed as open and have now been addressed:

- Removed active `decision` / human-review-era runtime surface from VLM prompt, model contract, API-facing types, and tests. Legacy nullable DB columns remain only for migration safety.
- Removed disclosure observation labels that were not grounded enough to keep as first-class tags.
- Separated raw OCR from cleaned OCR in the worker flow. Raw OCR remains `ocr`; advisory correction sources now use `ocr_cleanup` / `glm_ocr`.
- Added per-ad transcript and OCR endpoints:
  - `GET /api/ads/{ad_id}/transcript`
  - `GET /api/ads/{ad_id}/ocr`
- Added aggregate stats and observation-tag filtering:
  - `GET /api/stats`
  - `risk_label` filters on ad list/search routes.
- Added evidence export:
  - `GET /api/ads/{ad_id}/export/evidence?format=json|html`
- Added Video-to-Storyboard Reverse Engineer MVP:
  - `POST /api/ads/{ad_id}/storyboard`
  - deterministic pHash/timestamp shot segmentation
  - OCR/transcript-grounded shot text, voiceover, transition, beat, narrative function
  - JSON + HTML artifacts under `data/out/{ad_id}/`
  - frontend Storyboard tab in the ad detail drawer
- Added Synthetic Creative Review Panel MVP:
  - `GET /api/creative-panel/personas`
  - `POST /api/ads/{ad_id}/creative-panel`
  - 3-6 local personas, evidence citations, moderator summary, clear simulated-review caveat
  - JSON artifact under `data/out/{ad_id}/`
  - frontend Review Panel tab in the ad detail drawer
- Removed the creative-attribute filter suggestion. Aspect ratio, voiceover, on-screen text, end card, and disclaimer density are not high-value standalone filters right now.

## Current Watchlist

### Related Ads Snapshot Persistence

Status: deferred

Related ads are currently computed live during aggregation and through `GET /api/ads/{ad_id}/similar`. That is enough for the UI and analyst workflow today.

Only add persistence if exports or reproducible reports need a historical snapshot of "related at classification time." If that becomes necessary, add either:

- a small `related_ads_json` snapshot on the classification/report artifact, or
- a normalized `ad_related_ads` table for cross-ad reporting.

### Storyboard Later Scope

Status: future enhancement

The MVP is useful, but the following should stay out of the critical path:

- Optical-flow camera motion labels: static, pan, tilt, push-in, pull-out, handheld.
- VLM-enriched shot type, camera angle, subject, setting, and mood.
- Campaign-level storyboard comparison.
- Queries such as "show ads that open with product close-up then price reveal."
- PowerPoint export for agency-style presentations.

### Synthetic Creative Review Panel Later Scope

Status: future enhancement

The MVP is intentionally framed as simulated creative review, not demographic research. Future additions should preserve that framing:

- Optional local LLM pass for richer persona wording, with deterministic fallback retained for tests.
- User-defined persona sets saved locally.
- Side-by-side panel comparison across multiple ads or campaign variants.
- Generic `analysis_reports` persistence only if storyboard, panel, tone, and export reports need shared history.

## Non-Goals

- No creative-attribute filter work unless a real analyst workflow needs it.
- No disclosure-label revival unless the labels are grounded as evidence-backed entities rather than broad risk tags.
- No demographic representativeness claims, fake response percentages, or market forecasts in synthetic panel output.
- No web research by default.
- No blocking, gating, escalation, or human-review queues.
