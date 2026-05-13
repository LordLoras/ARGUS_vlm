# Pipeline & Demo Analysis

## Critical Accuracy Issues

### A1. Short brand names silently dropped from products
**File**: `ad_classifier/vlm/validation.py:48-49`

`_product_in_evidence` requires at least one token >= 4 chars to appear in the evidence blob. Short brand names like "Ram", "GMC", "BMW", "Kia", "Audi" score 0 matches and are silently removed. The `_KNOWN_SHORT_WORDS` list (line 83-86) doesn't include most 3-letter automotive brands.

**Fix**: Add common short brand names to `_KNOWN_SHORT_WORDS`, and also check against VLM evidence items (source="vlm") in addition to OCR/transcript.

### A2. VLM structured offer data discarded during aggregation
**File**: `ad_classifier/pipeline/aggregation/policy.py:201-206`

When mapping VLM `VLMOffer` objects to `OfferEntity`, only `o.value or o.type` is preserved as text. The VLM's structured fields — `expiry_text`, `expiry_resolved`, `promo_code`, `scarcity_signals`, `urgency_signals` — are all silently thrown away. These are the most valuable marketing intelligence fields (offer expiry dates, promo codes, urgency tactics).

**Fix**: Map VLM offer fields into `OfferTerms`. At minimum, extract `promo_code` → `offer_terms.promo_codes`, `expiry_text`/`expiry_resolved` → `offer_terms.expiry`, and `scarcity_signals`/`urgency_signals` → `offer_terms.scarcity_signals`/`offer_terms.urgency_signals`.

### A3. `_parse_rating_count` produces garbage from formatted strings
**File**: `ad_classifier/pipeline/aggregation/policy.py:416-420`

Strips all non-digit characters. "4.7 out of 5 (2,341 ratings)" → `472341` instead of `2341`. "1.2K" → `12`.

**Fix**: Use regex: `re.search(r'[\d,]+', value)` for the count portion, then strip commas. Handle K/M suffixes.

### A4. Brand validation no-op — ungrounded brands kept
**File**: `ad_classifier/vlm/validation.py:41-44`

When `_brand_in_evidence` returns False, the code does `pass` instead of clearing or flagging the brand. The validation check is completely bypassed.

**Fix**: Replace `pass` with logic that clears the brand (`me.brand.name = None`) or reduces confidence.

---

## High-Severity Accuracy Issues

### A5. OCR cleanup replaces in-memory data; raw vs cleaned inconsistency
**File**: `ad_classifier/worker/stages.py:112-127`

Original OCR items are saved to DB, then the in-memory list is replaced with VLM-cleaned items. All downstream consumers (rules engine, evidence bundle, marketing extraction) use cleaned OCR. The API `/ads/{id}/frames` returns original PaddleOCR items, but FTS search uses cleaned text — inconsistency.

**Fix**: Maintain dual OCR lists. Use originals for evidence validation; cleaned for FTS and marketing extraction. Or write VLM-corrected items with `engine="vlm_corrected"` so both are queryable.

### A6. European locale price misinterpretation
**File**: `ad_classifier/marketing/offer_extraction.py:326-332`

`_parse_amount` treats `"1.200"` as 1200.0 (US comma-thousands). In EU locales this means 1.20 Euros. Only US-locale ads with `$1,200`-style formatting should use comma-thousands.

**Fix**: Only apply comma-thousands parsing when a currency symbol is present. Add locale awareness or at minimum require `$`/`€`/`£` prefix.

### A7. Auto-specific price filters applied to all categories
**File**: `ad_classifier/vlm/validation.py:95-114`

`_NON_PRICE_CONTEXT` includes auto-dealership terms (cash allowance, dealer fee, per $1,000 financed). For non-automotive ads (furniture, insurance), legitimate prices get suppressed.

**Fix**: Gate `_filter_non_vehicle_prices` behind `primary_category == "automotive"`.

### A8. OCR dedup always keeps first frame, losing later higher-quality text
**File**: `ad_classifier/vlm/verifier.py:331-354`

`_dedupe_ocr_text` marks later occurrences as duplicates and replaces with "(repeats above)". But later frames (e.g., end cards with full legal text) often have more complete OCR than earlier partial views.

**Fix**: When deduplicating, keep the version with longer text rather than always keeping the first occurrence.

### A9. VLM salvage parser can match keys inside string values
**File**: `ad_classifier/vlm/verifier.py:124-174`

`raw.find('"marketing_entities"')` can match inside a string like `"summary": "The ad includes marketing_entities such as..."`, causing garbage parsing.

**Fix**: Search for `"marketing_entities": {` (key followed by object start) instead of bare key name.

### A10. Character-level similarity metric over-deduplicates distinct offers
**File**: `ad_classifier/marketing/offer_extraction.py:591-599`

`_text_similarity_ratio` counts character overlap divided by longer string length. Two completely different offers with shared vocabulary ("0% APR financing" vs "0% APR for 60 months") score very highly and get deduped incorrectly.

**Fix**: Use token-level Jaccard similarity or Levenshtein distance ratio instead.

---

## Medium-Severity Issues

### A11. Brand normalization mangles known brand capitalization
**File**: `ad_classifier/marketing/brand.py:52-55`

`_title_case` turns "IPHONE" → "Iphone" (should be "iPhone"), "MACBOOK" → "Macbook" (should be "MacBook"). The alias map is too small (6 brands).

**Fix**: Expand `brands_aliases.yaml` significantly, especially for tech and automotive brands.

### A12. VLM `decision` field computed but never persisted
The `decision` column exists in the `ads` DB table and VLM returns it, but `aggregate()` never writes it. Dead column.

**Fix**: Either remove the column and VLM field, or persist the VLM decision.

### A13. 320px image compression makes small VLM text unreadable
**File**: `ad_classifier/vlm/verifier.py:305-319`

`_encode_image` resizes to max 320px at 85% JPEG quality. For ad disclaimer text, phone numbers, and URLs, this can make critical detail illegible to the VLM.

**Fix**: Make `max_dim` and JPEG quality configurable. Consider 512px for text-heavy categories or as a second zoom pass.

### A14. Self-correction index-based removal has no bounds checking
**File**: `ad_classifier/vlm/correction.py:122-132`

`prices_to_remove`, `offers_to_remove`, `ctas_to_remove` are used as direct list indices without bounds validation. Off-by-one LLM errors silently remove wrong items.

**Fix**: Add bounds checking and log out-of-range indices.

---

## Demo-Feature Gaps (Highest Impact for Marketing Researchers)

### D1. `related_ads` computed but never persisted
**File**: `ad_classifier/worker/stages.py:202-208`

`enrich_related_ads()` computes similarity verdicts (near_duplicate, same_campaign_different_offer, etc.) but they're never written to the DB. The `/ads/{id}/similar` endpoint re-computes on the fly with potentially different results.

**Impact**: This is the most valuable competitive intelligence data — "show me ads that are variants of the same campaign." It's computed and thrown away.

**Fix**: Persist `related_ads` results. Add a `related_ads` table or store as JSON in the classification.

### D2. No aggregate statistics endpoint
There's no API endpoint for: category distribution, brand frequency, offer type counts, average prices, risk label distribution, or any dashboard-worthy statistics. The agent can do `aggregate` via SQL, but the REST API can't.

**Impact**: Marketing researchers need "how many ads mention brand X" or "most common offers in automotive."

**Fix**: Add `/api/stats` endpoint returning pre-computed aggregates (category counts, brand counts, offer type distribution, CTA distribution, risk label distribution).

### D3. Transcript segments not in API
Transcript data (speech content with timestamps) is stored but has no API endpoint.

**Fix**: Add `/ads/{id}/transcript` endpoint.

### D4. OCR items not queryable per-ad through a direct endpoint
OCR items require joining through frame IDs. No direct `/ads/{id}/ocr` endpoint exists.

**Fix**: Add `/ads/{id}/ocr` endpoint that returns all OCR items for an ad.

### D5. No sentiment/tone detection
The VLM sees every ad but never reports emotional strategy (aspirational, humorous, urgent, fear-based, comforting). This is core marketing intelligence.

**Fix**: Add `tone` field to `MarketingEntities` and `CreativeAttributes`, prompt the VLM to classify ad tone.

### D6. No target audience/demographic inference
The VLM could estimate target demographics (age range, gender, lifestyle segment) from ad content. Not currently extracted.

**Fix**: Add `target_audience` field to `MarketingEntities`, prompt VLM for audience inference.

### D7. Creative attributes not filterable
`creative_attributes` (format, aspect_ratio, voiceover, disclaimer_density) are stored but have no API filter. Researchers can't query "show me all before_after ads" or "ads with disclaimer_density=high."

**Fix**: Add `creative_format`, `has_voiceover`, `disclaimer_density` as query params on `/ads`.

### D8. Risk labels not searchable via REST
`risk_labels` stored as JSON array with no index and no API filter. Agent can query via SQL, but REST API cannot.

**Fix**: Add `risk_labels` filter to `/ads` endpoint query params.

---

## Quick Wins (Highest Impact / Lowest Effort)

| Priority | Item | Effort | Impact |
|----------|------|--------|--------|
| 1 | Persist related_ads to DB | 2h | ★★★★★ — "show me campaign variants" is the killer demo feature |
| 2 | Add `/api/stats` aggregation endpoint | 3h | ★★★★★ — dashboard-ready data |
| 3 | Map VLM offer fields into OfferTerms (A2) | 2h | ★★★★☆ — offer expiry, promo codes, urgency are gold for researchers |
| 4 | Fix brand validation no-op (A4) | 15min | ★★★★☆ — brands appearing when they shouldn't |
| 5 | Fix rating count parsing (A3) | 30min | ★★★☆☆ — garbage numbers undermine credibility |
| 6 | Add sentiment/tone to VLM prompt | 2h | ★★★★☆ — emotional strategy is what researchers care about |
| 7 | Add target audience to VLM prompt | 2h | ★★★★☆ — "who is this ad targeting?" is a top research question |
| 8 | Improve OCR dedup to keep longer text (A8) | 1h | ★★★☆☆ — end-card legal text gets lost |
| 9 | Make image resolution configurable (A13) | 1h | ★★★☆☆ — small text legibility directly affects accuracy |
| 10 | Add `/ads/{id}/transcript` and `/ads/{id}/ocr` endpoints | 2h | ★★★☆☆ — makes full ad data accessible |