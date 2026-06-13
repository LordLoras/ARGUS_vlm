# ARGUS Search Demo Queries

Tested against the live local API on 2026-06-13:

`GET http://127.0.0.1:8000/api/search?mode=...&q=...&k=20&rerank=true`

Use these without brand/category filters unless noted. They are selected because
they return a clean result set in the current demo database.

## Best Visual Queries

### Visual: legal ad scene

- Mode: `Visual`
- Query: `lawyer outside office phone number`
- Expected result: 1 result, Sweet James legal ad (`ad_01f9e9b0`)
- Why it works: this is a visually specific scene with a person outside an office
  and large phone-number text. It avoids the noisy automotive cluster.

### Visual: TV promo scene

- Mode: `Visual`
- Query: `tv show weathered paper note next friday fishing boat`
- Expected result: 1 result, Discovery / Deadliest Catch (`ad_cc0dd3ea`)
- Why it works: combines visual texture, object context, and visible promo text.
  This is a good replacement for broad vehicle queries.

## One Clean Query Per Search Mode

### Keyword

- Mode: `Keyword`
- Query: `lifetime oil changes family savings event`
- Expected result: 1 result, Fred Anderson Toyota (`ad_36547a2b`)
- Demo point: exact OCR/entity text retrieval. Good for showing deterministic
  searchable extracted text.

### Text Vector

- Mode: `Text vector`
- Query: `television show fishing boat next friday`
- Expected result: 1 result, Discovery / Deadliest Catch (`ad_cc0dd3ea`)
- Demo point: semantic text embedding search over ad transcript, OCR, and entity
  text. This is clean even without brand filters.

### Hybrid

- Mode: `Hybrid`
- Query: `legal help after getting hurt call attorney`
- Expected result: 1 result, Sweet James legal ad (`ad_01f9e9b0`)
- API strategy observed: `hybrid_rrf`
- Demo point: natural-language paraphrase retrieval. This shows hybrid/vector
  fallback rather than just exact keyword matching.

### Visual + OCR

- Mode: `Visual + OCR`
- Query: `five year price guarantee satellite coverage`
- Expected result: 1 result, T-Mobile T-Satellite / Experience plans (`ad_203a2d73`)
- API strategy observed: `visual_ocr_rrf`
- Demo point: OCR-heavy offer retrieval fused with visual search machinery.

Alternative Visual + OCR query:

- Mode: `Visual + OCR`
- Query: `free gift with purchase valued up to 134 beauty cream`
- Expected result: 1 result, Lancome / Absolue cream ad (`ad_e7b406e5`)

## Avoid For Clean No-Filter Demo

- Mode: `Visual`
- Query: `black pickup truck dust road`
- Observed result: 18 automotive results with `k=20`
- Reason: the demo database is heavily automotive, and the visual threshold is
  intentionally permissive. This query is only clean if you also set
  Brand = `Jeep`.

## Suggested Live Demo Order

1. Start with `Visual` and run `lawyer outside office phone number`.
2. Stay in `Visual` and run `tv show weathered paper note next friday fishing boat`.
3. Switch to `Keyword` and run `lifetime oil changes family savings event`.
4. Switch to `Text vector` and run `television show fishing boat next friday`.
5. Switch to `Hybrid` and run `legal help after getting hurt call attorney`.
6. Switch to `Visual + OCR` and run `five year price guarantee satellite coverage`.

