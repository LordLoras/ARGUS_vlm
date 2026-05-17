# ARGUS Suggestions and Roadmap

Last updated: 2026-05-17

This file tracks current product and implementation suggestions against the scope described in `getting_started.html` and `technical_detail.html`.

## Scope Guardrails

ARGUS is a local-first ad intelligence system. Suggestions should preserve these boundaries:

- Keep ingestion, OCR, transcript alignment, VLM classification, marketing entities, embeddings, search, campaigns, and the read-only agent as the core product.
- Keep the classification path categorization-only. Do not add approve, block, flag, escalation, or human-review workflows.
- Treat risk labels as descriptive observation tags for search and analysis.
- Keep the frontend decoupled from the backend through JSON endpoints and SSE.
- Keep optional creative-analysis features downstream of persisted evidence so they do not block core ingestion/classification.
- Keep research local-first. Internet research remains out of scope until a controlled web research layer exists.

## Current Open Technical Debt

### T1. Remove remaining `decision` / review-era surface area

Status: open

The project goal says there is no decisioning layer, but legacy `decision` and `needs_human_review` fields still appear in the SQLite schema, generated frontend types, VLM tests, and some model surfaces. `ClassificationRepository` already drops these fields, which is directionally correct, but the remaining schema/API/frontend traces are confusing.

Recommended next step:

- Remove user-facing and API-facing `decision` usage.
- Keep a migration-safe approach for existing databases, either by leaving nullable legacy columns unused or adding a cleanup migration if practical.
- Update VLM prompt/tests away from allow/review wording.

### T2. Separate raw OCR from cleaned OCR through the pipeline

Status: open

Raw PaddleOCR is persisted, and `raw_ocr_items.json` is written before cleanup, but after OCR cleanup the in-memory pipeline uses cleaned OCR for rules, evidence text collection, validation, embeddings, and marketing enrichment. This weakens the "raw OCR is preserved exactly" rule for downstream reasoning.

Recommended next step:

- Thread both `raw_ocr_items` and `corrected_ocr_items` through rules/evidence/VLM/search decisions.
- Persist or expose corrected OCR separately instead of replacing the working list.
- Make evidence source labels explicit: `ocr` for raw OCR, `ocr_cleanup` or `glm_ocr` for advisory corrections.

### T3. Related ads are live-computed, not snapshotted

Status: mostly acceptable

The worker computes `related_ads` during aggregation and `/api/ads/{ad_id}/similar` computes similar ads live. That is enough for the UI today. Persistence is only needed if ARGUS needs a historical snapshot of "related at classification time."

Recommended next step:

- Do not prioritize persistence unless exports or reproducible reports need it.
- If needed later, add a small `related_ads_json` snapshot or a normalized `ad_related_ads` table.

## Near-Term API and UI Gaps

These are higher-value than adding new AI demos because they expose evidence ARGUS already stores.

| Priority | Item | Status | Why it matters |
|---|---|---|---|
| 1 | Per-ad transcript endpoint | Open | The DB stores `transcript_segments`, but the ad detail API does not expose them directly. |
| 2 | Per-ad OCR endpoint | Open | Analysts need raw OCR and optional OCR-VL text by frame. |
| 3 | Aggregate stats endpoint | Open | Dashboards should not fetch many ad details just to count brands, categories, tags, or statuses. |
| 4 | Risk-label REST filters/search | Open | Observation tags are important analyst fields but are not first-class REST filters. |
| 5 | Evidence export | Open | Useful for demos, QA, and analyst handoff: JSON/HTML bundle with frames, OCR, transcript, entities, and classification. |

## New Feature Candidate: Video-to-Storyboard Reverse Engineer

Recommendation: add after core evidence APIs are cleaned up.

This is a strong demo and fits ARGUS well. It uses data the pipeline already creates: frames, transcript segments, OCR, keyframe selection, VLM reasoning, and campaign context. It should be an optional creative-analysis module, not part of the required classification path.

### MVP Scope

- Segment the ad into shots using frame difference, pHash changes, scene-change signals, and transcript timing.
- Store or return shot records with:
  - `start_ms`, `end_ms`, `duration_ms`
  - representative frame path
  - transition guess: `cut`, `fade`, `dissolve`, `unknown`
  - on-screen text from OCR/OCR-VL
  - nearby voiceover/transcript
  - shot type, camera angle, subject, setting, and mood from VLM
  - emotional beat and narrative function from LLM
- Generate an HTML storyboard export before PDF/deck export.
- Add API endpoint such as `POST /api/ads/{ad_id}/storyboard`.
- Add frontend tab/action from the ad detail view.

### Later Scope

- Optical-flow camera motion labels: static, pan, tilt, push-in, pull-out, handheld.
- Campaign-level storyboard comparison.
- Queries such as "show ads that open with product close-up then price reveal."
- PowerPoint export for agency-style presentations.

### Implementation Notes

- Suggested package: `ad_classifier/creative/storyboard/`.
- Suggested models: `Storyboard`, `StoryboardShot`, `ShotCamera`, `ShotBeat`.
- Suggested persistence: start with `data/out/{ad_id}/storyboard.json`; add tables only when the UI needs filtering across storyboards.
- Tests should cover shot boundary heuristics, transcript alignment, JSON schema validation, and export rendering.

## New Feature Candidate: Synthetic Creative Review Panel

Recommendation: add later, but frame it carefully.

This should not be presented as a real focus group or statistically valid demographic research. AI personas are useful for creative stress testing, message clarity checks, objection discovery, and A/B-test ideation. They are not consumer truth.

Use the name "Synthetic Creative Review Panel" instead of "Synthetic Focus Group" in product/UI copy.

### MVP Scope

- User selects 3-6 configured personas, such as:
  - budget-conscious parent
  - skeptical health buyer
  - luxury shopper
  - first-time car buyer
  - Gen Z mobile-first viewer
  - compliance-minded reviewer
- Each persona receives the persisted evidence bundle, not unrestricted raw claims:
  - transcript
  - OCR/OCR-VL
  - selected frames
  - classification
  - marketing entities
  - offers, prices, CTAs, disclaimers
- Each persona returns:
  - first impression
  - understood product/offer
  - emotional reaction
  - trust or confusion points
  - likely objection
  - most memorable frame/line
  - CTA likelihood as qualitative text, not a fake probability
- A moderator LLM summarizes:
  - consensus
  - disagreements
  - message clarity issues
  - strongest hooks
  - suggested A/B variants

### Guardrails

- Do not infer protected or sensitive real audience traits as facts.
- Do not claim representativeness.
- Do not output "market will respond X%."
- Label outputs as simulated creative review.
- Keep the analysis local-first and auditable by citing evidence timestamps and ad IDs.

### Implementation Notes

- Suggested package: `ad_classifier/creative/panel/`.
- Suggested endpoint: `POST /api/ads/{ad_id}/creative-panel`.
- Suggested persistence: use a generic `analysis_reports` table later if storyboard, panel, tone, and export reports all need storage.
- Tests should cover persona prompt construction, evidence grounding, no fabricated ad IDs, and schema validation.

## Priority Order

1. Clean scope drift around `decision` and review-era language.
2. Expose transcript, OCR, risk labels, and evidence export through proper APIs.
3. Fix raw-vs-cleaned OCR data flow.
4. Add Storyboard Reverse Engineer as the first premium creative-analysis feature.
5. Add Synthetic Creative Review Panel after storyboard, with strong UI caveats.
6. Consider sentiment/tone labels only as grounded creative descriptors, not demographic truth.
