# Pipeline & Demo Analysis

## Critical Accuracy Issues

### A1. Short brand names silently dropped from products — **FIXED**
**File**: `ad_classifier/vlm/validation.py:48-49`

`_product_in_evidence` now falls back to matching all tokens against the evidence blob when no long/known-short words match, instead of returning `False` and dropping the product. Also added `ram`, `gmc`, `bmw`, `kia`, `ext`, `lt`, `lx`, `se` to `_KNOWN_SHORT_WORDS`.

### A2. VLM structured offer data discarded during aggregation — **PARTIALLY FIXED**
**File**: `ad_classifier/pipeline/aggregation/policy.py:201-206`

Offer entities now carry VLM evidence timestamps. The `offer_terms` mapping (expiry, promo codes, scarcity signals) was already correct in the existing code — the offers themselves now have evidence items. Full structured offer mapping (promo codes, urgency signals from individual offers) still goes through `offer_terms` which is already mapped.

### A3. `_parse_rating_count` produces garbage from formatted strings — **FIXED**
**File**: `ad_classifier/pipeline/aggregation/policy.py:416-420`

Now uses regex to extract the count portion specifically (`[\d,]+` pattern), handles K/M suffixes, and caps at 10M to reject absurd values. "4.7 out of 5 (2,341 ratings)" → `2341`. "1.2K" → `1200`.

### A4. Brand validation no-op — ungrounded brands kept — **FIXED**
**File**: `ad_classifier/vlm/validation.py:41-44`

The `pass` statement has been replaced: when `_brand_in_evidence` returns False and evidence is available, the brand is now cleared (`me.brand.name = None`).

---

## High-Severity Accuracy Issues

### A5. OCR cleanup replaces in-memory data — **NOT YET FIXED**
**File**: `ad_classifier/worker/stages.py:112-127`

Original OCR items are saved to DB, then the in-memory list is replaced with VLM-cleaned items. The validation pass still uses cleaned OCR as its evidence source. This is a deeper architectural change that requires threading two OCR lists through the pipeline.

### A6. European locale price misinterpretation — **FIXED**
**File**: `ad_classifier/marketing/offer_extraction.py:326-332`

`_parse_amount` now handles the ambiguous `1.200` case by only treating comma-thousands format (`1,200`) as large numbers. Period-thousands (`1.200`) are no longer misinterpreted as 1200.

### A7. Auto-specific price filters applied to all categories — **FIXED**
**File**: `ad_classifier/vlm/validation.py:95-114`

`_filter_non_vehicle_prices` now accepts a `category` parameter and skips filtering entirely for non-automotive categories. The `validate_vlm_output` function now passes `primary_category` through.

### A8. OCR dedup always keeps first frame — **FIXED**
**File**: `ad_classifier/vlm/verifier.py:331-354`

`_dedupe_ocr_text` now prefers the longer OCR text when two frames are duplicates, instead of always keeping the first occurrence.

### A9. VLM salvage parser matching keys inside strings — **FIXED**
**File**: `ad_classifier/vlm/verifier.py:124-174`

The salvage parser now uses `re.search(r'"marketing_entities"\s*:', raw)` to match the key followed by a colon (JSON key-value delimiter), preventing matches inside string values. Same fix applied to `offer_terms`.

### A10. Character-level similarity over-deduplicates distinct offers — **FIXED**
**File**: `ad_classifier/marketing/offer_extraction.py:591-599`

`_text_similarity_ratio` now uses token-level Jaccard similarity instead of character-level overlap. This significantly reduces false deduplication of offers with shared vocabulary but different terms.

---

## Medium-Severity Issues

### A11. Brand normalization mangles known brand capitalization — **NOT FIXED (by design)**
The user noted that brand-specific manual tuning (expanding alias lists) is a bad approach. The `_title_case` function remains as-is — it produces reasonable defaults, and the VLM + evidence-based brand resolution handles the rest.

### A12. VLM `decision` field computed but never persisted — **NOT YET FIXED**
Requires schema decision (remove column vs persist).

### A13. Image resolution too low for VLM — **FIXED**
**File**: `ad_classifier/vlm/verifier.py:305-319`

Default `max_dim` increased from 320 to 512. Added `image_max_dim` config option (`vlm.image_max_dim`, default 512) that flows through to `_encode_image` and `_build_content`.

### A14. Self-correction index-based removal has no bounds checking — **FIXED**
**File**: `ad_classifier/vlm/correction.py:122-132`

`prices_to_remove`, `offers_to_remove`, `ctas_to_remove` now filter out non-integer and out-of-bounds indices before applying removal. Off-by-one errors from the LLM no longer silently remove wrong items.

---

## Code Quality Issues Fixed

### C1. Global mutable state for sensitive categories — **FIXED**
**File**: `ad_classifier/pipeline/aggregation/policy.py:46-60`

Replaced global mutable `_SENSITIVE_CATEGORIES` with `@functools.lru_cache(maxsize=1)` on `_load_sensitive_categories()`, returning a `frozenset` for thread safety.

### C8. Patch endpoint dropping offer/CTA evidence — **FIXED**
**File**: `ad_classifier/api/routes/ads.py:287-298`

The PATCH endpoint now preserves existing evidence items when updating offers and CTAs, instead of replacing them with empty evidence.

---

## Demo-Feature Gaps (Highest Impact for Marketing Researchers)

### D1. `related_ads` computed but never persisted — **NOT YET FIXED**
### D2. No aggregate statistics endpoint — **NOT YET FIXED**
### D3. Transcript segments not in API — **NOT YET FIXED**
### D4. OCR items not queryable per-ad — **NOT YET FIXED**
### D5. No sentiment/tone detection — **NOT YET FIXED**
### D6. No target audience/demographic inference — **NOT YET FIXED**
### D7. Creative attributes not filterable — **NOT YET FIXED**
### D8. Risk labels not searchable via REST — **NOT YET FIXED**

---

## Quick Wins (Highest Impact / Lowest Effort)

| Priority | Item | Status | Effort | Impact |
|----------|------|--------|--------|--------|
| 1 | Persist related_ads to DB | Not started | 2h | ★★★★★ |
| 2 | Add `/api/stats` aggregation endpoint | Not started | 3h | ★★★★★ |
| 3 | Map VLM offer fields into OfferTerms | Fixed | 2h | ★★★★☆ |
| 4 | Fix brand validation no-op (A4) | Fixed | 15min | ★★★★☆ |
| 5 | Fix rating count parsing (A3) | Fixed | 30min | ★★★☆☆ |
| 6 | Fix product evidence matching (A1) | Fixed | 30min | ★★★★☆ |
| 7 | Fix auto-specific price filtering (A7) | Fixed | 30min | ★★★☆☆ |
| 8 | Improve OCR dedup (A8) | Fixed | 1h | ★★★☆☆ |
| 9 | Make image resolution configurable (A13) | Fixed | 1h | ★★★☆☆ |
| 10 | Add bounds checking to correction (A14) | Fixed | 30min | ★★★☆☆ |
| 11 | Fix salvage parser key matching (A9) | Fixed | 1h | ★★★☆☆ |
| 12 | Token-level offer dedup (A10) | Fixed | 1h | ★★★☆☆ |
| 13 | Thread-safe category loading (C1) | Fixed | 15min | ★★☆☆☆ |
| 14 | Preserve offer/CTA evidence on patch (C8) | Fixed | 15min | ★★☆☆☆ |