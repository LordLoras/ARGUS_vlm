# ARGUS Suggestions and Roadmap

Last updated: 2026-05-17

This file tracks active product and implementation suggestions against the scope described in `getting_started.html` and `technical_detail.html`.

## Scope Guardrails

ARGUS remains a local-first ad intelligence system:

- Keep ingestion, OCR, transcript alignment, VLM classification, marketing entities, embeddings, search, campaigns, and the read-only agent as the core product.
- Keep the classification path categorization-only. Do not add approve, block, flag, escalation, or human-review workflows.
- Treat risk labels as descriptive observation tags for search and analysis.
- Keep optional creative-analysis reports downstream of persisted evidence so they do not block ingestion or classification.
- Keep research local-first. Internet research remains out of scope until a controlled web research layer exists.
- Do not present simulated persona output as representative consumer research.

## Highest-Wow Demo Candidates

### 1. Creative DNA Fingerprint

Status: proposed

Build a one-page "creative genome" for every ad: hook style, narrative arc, visual density, offer mechanics, brand presence, CTA style, emotional beat sequence, pacing, and repeated motifs. This turns one ad into a compact creative strategy profile.

Why it is strong:

- Agencies immediately understand it as "what makes this ad work."
- It creates a reusable feature vector for comparing ads beyond category or brand.
- It makes ARGUS feel like a creative intelligence product, not just an extractor.

MVP:

- Add `ad_classifier/creative/dna/`.
- Generate `creative_dna.json` from frames, transcript, OCR, marketing entities, and classification evidence.
- Show a compact radar/profile panel in the ad detail drawer.
- Add agent tool support for questions like "show me ads with offer-first DNA" or "which brands use proof-heavy endings?"

### 2. Counterfactual Creative Lab

Status: proposed

Let the user ask "what if this ad opened with the offer instead of the brand?" or "make this CTA clearer" and get a grounded alternate script/shot-plan, plus a diff against the original extraction.

Why it is strong:

- It uses the existing evidence as source material, so it is practical and auditable.
- It creates a demo moment: original ad -> alternate script -> changed entities/CTA/beat.
- It stays local-first if powered by the local LLM.

Guardrail:

- Do not predict sales lift or real consumer response.
- Label outputs as generated creative alternatives.

MVP:

- Input: ad id + rewrite goal.
- Output: alternate script, alternate shot list, changed CTA/offer/beat fields, and citations to source evidence.
- Store under `data/out/{ad_id}/counterfactuals/{report_id}.json`.

### 3. Competitive White-Space Map

Status: proposed

Create an interactive map of ads by semantic/visual similarity, then overlay campaign, brand, category, offer type, hook type, and creative DNA. The killer demo is "show me where all local automotive ads cluster, and which creative territories nobody is using."

Why it is strong:

- It makes embeddings tangible.
- It helps agencies pitch positioning and creative differentiation.
- It turns the database into a visual strategy board.

MVP:

- Use persisted text + visual vectors and UMAP/t-SNE locally.
- Generate a 2D coordinate cache per ad.
- Add a frontend map view with hover preview, brand/category coloring, and cluster labels from local LLM or deterministic keywords.
- Add "white-space notes" that describe sparse neighborhoods without claiming market opportunity as fact.

### 4. Hook and Payoff Analyzer

Status: proposed

Analyze the first 3 seconds, middle proof section, and final CTA/payoff. Score only structural clarity, not quality: hook presence, product clarity, offer timing, proof timing, CTA timing, and end-card readability.

Why it is strong:

- It is instantly useful for creative review.
- It avoids vague sentiment and focuses on observable structure.
- It pairs well with Creative DNA Fingerprint.

MVP:

- Derive timings from frame timestamps, transcript segments, OCR density, and marketing entities.
- Output a timeline with labels: hook, product reveal, offer reveal, proof, CTA, terms.
- Add an agent answer template: "The ad waits 18.5s before the first explicit CTA."

### 5. Promise Match: Ad vs Landing Page

Status: proposed

When optional landing-page metadata exists, compare the ad promise against the landing page: product, price, offer, CTA, disclaimer/terms, phone/URL, and brand identity. This is not a compliance gate; it is a consistency report.

Why it is strong:

- High-value for agencies and performance marketers.
- Uses existing structured marketing entities.
- Creates a concrete "handoff quality" report.

MVP:

- Add `ad_classifier/creative/promise_match/`.
- Compare ad marketing entities against optional landing-page metadata.
- Output matched, missing, changed, and ambiguous fields with evidence citations.
- Add exportable HTML report.

### 6. Auto Pitch Deck Generator

Status: proposed

Generate a local PowerPoint-style strategy deck from a campaign or selected ads: campaign overview, key ads, frame strips, creative DNA comparison, extracted offers/CTAs, related ads, synthetic panel summary, and next-test ideas.

Why it is strong:

- It turns ARGUS outputs into an artifact agencies already sell.
- It shows the value of all earlier modules in one deliverable.
- It is demo-friendly and shareable.

MVP:

- Start with HTML export before `.pptx`.
- Use existing creative panel and future Creative DNA artifacts when present.
- Add a campaign-level endpoint such as `POST /api/campaigns/{campaign_id}/deck`.

### 7. Multimodal Moment Search

Status: proposed

Let users search for exact moments inside ads, not just ads: "show frames where a price appears," "find shots with a product close-up and no voiceover," "find CTAs after 20 seconds," "show me red truck shots that mention APR."

Why it is strong:

- It makes ARGUS feel like a searchable creative memory.
- It uses data already stored per frame and transcript segment.
- It bridges visual embeddings, OCR, transcript, and frame-level timing.

MVP:

- Add `moments` search endpoint returning frame/shot-level hits.
- Use frame visual vectors, OCR text, transcript overlap, and timestamp windows.
- UI: search results as timestamped clips/frames, not just ad rows.

### 8. Campaign Drift Detector

Status: proposed

Track how a campaign changes over time: new products, offer changes, CTA changes, disclaimer/terms changes, visual motif changes, and creative DNA shifts.

Why it is strong:

- Great for campaign tracking, not just one-off ad analysis.
- It creates longitudinal insight from local persisted data.
- It helps answer "what changed this week?"

MVP:

- Compare ads assigned to a campaign by ingestion date.
- Produce timeline events from entity diffs, Creative DNA diffs, and vector movement.
- Add agent support for "summarize creative drift for this campaign."

## Existing Feature Enhancements

### Synthetic Creative Review Panel Enhancement Path

Status: future enhancement

- Add optional local LLM pass for richer persona wording, with deterministic fallback retained for tests.
- Add user-defined persona sets saved locally.
- Add side-by-side panel comparison across multiple ads or campaign variants.
- Keep all output framed as simulated creative review.

### Related Ads Snapshot Persistence

Status: deferred

Related ads are currently computed live during aggregation and through `GET /api/ads/{ad_id}/similar`. That is enough for the UI and analyst workflow today.

Only add persistence if exports or reproducible reports need a historical snapshot of "related at classification time." If that becomes necessary, add either:

- a small `related_ads_json` snapshot on the classification/report artifact, or
- a normalized `ad_related_ads` table for cross-ad reporting.

## Recommended Build Order

1. Creative DNA Fingerprint.
2. Hook and Payoff Analyzer.
3. Multimodal Moment Search.
4. Competitive White-Space Map.
5. Campaign Drift Detector.
6. Promise Match.
7. Counterfactual Creative Lab.
8. Auto Pitch Deck Generator.

## Non-Goals

- No creative-attribute filter work unless a real analyst workflow needs it.
- No disclosure-label revival unless labels are grounded as evidence-backed entities rather than broad risk tags.
- No demographic representativeness claims, fake response percentages, or market forecasts in synthetic panel output.
- No web research by default.
- No blocking, gating, escalation, or human-review queues.
