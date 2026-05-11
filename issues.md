# Issues, Problems & Suggestions

### 2. Config uses Qwen3.6 for verifier but Gemma for the agent — not documented

- **File:** `config.yaml:62-72, 116-118`
- **Problem:** The VLM verifier is configured with `Qwen3.6-27B-Q4_K_M` while the NL agent uses `google/gemma-4-26b-a4b`. These are very different architectures with different capabilities (vision vs. text-only, context window sizes, etc.). There's no documentation explaining why different models are used or which capabilities are required from each.

---

## Ground Truth / Video-Only Analysis Issues

### 6. VLM can hallucinate entities not present in video

- **Files:** `ad_classifier/vlm/verifier.py`, `prompts/gemma_ad_verifier.txt`
- **Problem:** While the prompt says "NO WORLD KNOWLEDGE" and "GROUNDING: Every single value you output must be directly supported by text visible in the frames or words audible in the transcript," VLMs are known to hallucinate. The `_salvage_vlm_result` method (`verifier.py:110`) tries to recover any usable JSON even when malformed, potentially accepting fabricated data. There is no post-hoc verification that extracted entities actually appear in OCR or transcript text.
- **Suggestion:** Add a validation layer that cross-references every VLM-extracted entity (brand, product, price, offer, CTA) against OCR text and transcript segments. Flag or drop entities with no evidence in the source material.

### 7. OCR cleanup pass can rewrite ground truth

- **File:** `ad_classifier/vlm/cleanup.py` (referenced in `stages.py:112-114`), `prompts/ocr_cleanup.txt`
- **Problem:** The OCR cleanup pass uses the VLM to "fix" garbled OCR text. This can silently replace actual OCR output (ground truth of what appears on screen) with the VLM's guess. The AGENTS.md rule *"Do not silently overwrite OCR text with VLM corrections. Store raw OCR and corrected OCR separately"* exists for this reason.
- **Suggestion:** Verify the cleanup pass stores original OCR text alongside corrections, and that the pipeline always preserves raw OCR for audit. Add a warning when corrections change meaning.

### 8. Visual verification is destructive, not additive

- **File:** `ad_classifier/vlm/visual_verify.py:133-140`
- **Problem:** When `brand_visible` is False, the code sets `me.brand.name = None` — destroying data. This is a destructive operation that assumes the VLM visual verification is always correct. The visual verify pass only checks 2-3 frames and can't see the full ad.
- **Fix:** Use a confidence-weighted merge instead of outright deletion. Flag disagreements rather than silently dropping data.

### 9. Marketing entity extraction trusts VLM over deterministic extraction

- **File:** `ad_classifier/marketing/commercial.py:26-97`
- **Problem:** When merging VLM entities with deterministic extraction, VLM values take precedence (e.g., `if not base.offers` uses VLM offers only, never merges). The deterministic pass only fills gaps. For "ground truth is what's in the video," the deterministic extraction (directly from OCR/transcript) should be the primary source, with VLM enriching but not overriding.

### 10. OCR confidence threshold discards usable text

- **Files:** `ad_classifier/marketing/extract.py:81,393`, `ad_classifier/marketing/offer_extraction.py:36,376-377`
- **Problem:** `_MIN_TRACKING_CONFIDENCE = 0.75` and `_MIN_COMMERCIAL_CONFIDENCE = 0.75` mean any OCR text with confidence below 75% is completely ignored for entity extraction. PaddleOCR on CPU often produces lower confidence on small, stylized, or overlaid text — exactly the text that contains offers, disclaimers, and CTAs. This systematically misses important content.

---

## Code Quality / Maintainability

### 11. File size violations (~400 line soft cap)

| File | Lines | Issue |
|---|---|---|
| `ad_classifier/marketing/offer_extraction.py` | 601 | ~50% over cap |
| `ad_classifier/worker/stages.py` | 502 | ~25% over cap |
| `ad_classifier/pipeline/aggregation/policy.py` | 454 | ~13% over cap |
| `ad_classifier/marketing/extract.py` | 400 | At cap |
| `ad_classifier/vlm/verifier.py` | 489 | ~22% over cap |
| `ad_classifier/agent/loop.py` | 384 | Close to cap |
| `ad_classifier/ingest/service.py` | 397 | Close to cap |

- **Recommendation:** Split `offer_extraction.py` (offer/dedup logic, disclaimer logic, price extraction — at least 3 separate concerns). Split `stages.py` (pipeline orchestration vs. helpers). Split `verifier.py` (HTTP client, JSON extraction, salvage, URL normalization all mixed).

### 12. VLM model hierarchy mirrors MarketingEntities — massive duplication

- **Files:** `ad_classifier/vlm/models.py` (~278 lines) vs. `ad_classifier/models/marketing.py` (~225 lines)
- **Problem:** Every marketing entity type (Brand, Price, Offer, CTA, etc.) has a `VLM`-prefixed version that exists purely to have `extra="ignore"` config. This is ~250 lines of boilerplate. Many field types are identical; the only difference is that VLM models use `BaseModel` with `extra="ignore"` while marketing models use `StrictModel`. The mapping between them (`policy.py:163-393`, ~230 lines) is another maintenance burden.
- **Suggestion:** Use a single model hierarchy with an `extra` config override via a mixin or base class. Or use `model_config` inheritance to avoid duplication.

### 13. Duplicated utility functions

- `_max_density()` defined in both `offer_extraction.py:98` and `commercial.py:100`.
- `_merge_strings()` defined in both `extract.py:385` and `commercial.py:130`.
- `_currency_symbol()`, `_format_price()` defined in both `policy.py:146-160` and `price_parsing.py:21-34`.
- `_compact_key()` usage: should be in a single shared utility module.

### 14. `_entity_evidence()` type annotation issue

- **File:** `ad_classifier/pipeline/aggregation/policy.py:57`
- **Problem:** `def _entity_evidence(items)` has no type annotation on the `items` parameter. This is a mypy gap.

### 15. `_density_rank` dict duplicated

- **Files:** `offer_extraction.py:95`, `commercial.py:23`
- Both define the same dictionary mapping `"none"` -> `0`, `"low"` -> `1`, etc.

---

## Fragile / Overly Broad Extraction Patterns

### 16. `_GENERIC_PRODUCT_PATTERN` is too broad

- **File:** `ad_classifier/marketing/offer_extraction.py:37-39`
- **Pattern:** `r"\b(?P<year>20\d{2})\s+(?P<name>[A-Z][A-Za-z]+(?:\s+[A-Z][A-Za-z0-9-]+){0,4})\b"`
- **Problem:** This will match anything that starts with 20XX and has capitalized words after it — addresses ("2026 Main Street"), dates ("2026 January"), years in disclaimers, model numbers, etc. There's no filtering to verify the extracted text is actually a product name.
- **Suggestion:** Add a negative filter for common non-product patterns (streets, months, etc.) and cross-reference against known product indicators (MSRP, pricing context, etc.).

### 17. `_PRICE_PATTERN` matches non-price numbers

- **File:** `ad_classifier/marketing/offer_extraction.py:17-20`
- **Pattern:** `r"(?<![\w$])(?P<currency>\$)\s*(?P<amount>\d{1,3}(?:[,.]\d{3})+|\d+)(?P<cents>\.\d{2})?(?![\w,.])"`
- **Problem:** This regex matches dollar amounts even in contexts like document fees, tax amounts, finance charges, discount percentages, etc. The `_NON_PRICE_CONTEXT` filter (`offer_extraction.py:148-153`) is a weak denylist that can't catch everything.
- **Suggestion:** Use a more context-aware approach — require price to appear near product names, MSRP, "sale", "only", "now" indicators rather than catching every `$number`.

### 18. Phone number regex too aggressive

- **File:** `ad_classifier/marketing/extract.py:33`
- **Pattern:** `r"\b(?:\+?1[\s.()-]*)?(?:\(?\d{3}\)?[\s.()-]*)\d{3}[\s.()-]*\d{4}\b"`
- **Problem:** This will match any 10-digit sequence with optional formatting — tracking IDs, order numbers, account numbers, VIN fragments. OCR noise with digits can produce false phone numbers.

### 19. URL regex matches non-URLs in OCR text

- **File:** `ad_classifier/marketing/extract.py:28-32`
- **Problem:** The URL regex will match fragments like "come.to" or "it.com" within larger OCR text. While `_ALLOWED_OCR_TLDS` provides some filtering, common domains like `.app`, `.dev`, `.ai`, `.cloud`, `.me`, `.pro`, `.live`, `.today`, `.store`, `.blog` are missing.

### 20. Hardcoded brand-specific text normalization

- **File:** `ad_classifier/marketing/ocr_normalize.py:9-27`
- **Problem:** The `normalize_ocr_text` function contains hardcoded brand-specific fixes:
  - `r"\bDickPoe\b"` → `"Dick Poe"` (specific dealership)
  - `r"\b(20\d{2})(?=JEEP)"` → split year from JEEP
  - `r"\b(20\d{2})(?=CHRYSLER)"` → split year from CHRYSLER
  - `r"\bJEEP(?=GRAND|WRANGLER|GLADIATOR)"` → insert space
  - `r"\bCHRYSLER(?=PACIFICA)"` → insert space
  - `r"\bGRANDCHEROKEE\b"` → `"GRAND CHEROKEE"`
  - Plus REBATE, MILITARY & FIRST RESPONDER, MOS, etc.
- **Problem:** This is dataset-specific normalization that won't generalize to other ad collections. It also duplicates logic in `policy.py:125-134` (`_normalize_rule_evidence_text`).
- **Suggestion:** Move to a configurable rule file or create a generic compound-word splitter. Extract dataset-specific rules from code.

---

## Pipeline & Data Flow Issues

### 21. `FinalAdClassification` spec output fields missing

- **Files:** `ad_classifier/pipeline/aggregation/models.py:35-49` vs. the JSON spec in AGENTS.md
- **Missing fields:**
  - `sensitive_category: bool`
  - `ocr_quality: OCRQuality`
  - `embeddings: dict` (text_model, visual_model, indexed_in)
  - `model_outputs: dict` (ocr, paddlevl, vlm)
  - `debug: dict` (selected_frames, dropped_frames, rules_triggered, dropped_labels)
  - `campaigns: list`
  - `related_ads.exact_duplicate_of`, `near_duplicate_of`
- **Problem:** The `aggregate()` function produces a model that doesn't match the output spec in AGENTS.md, making the API response inconsistent with the documentation.

### 22. `ClassificationRecord` also missing fields from the spec

- **File:** `ad_classifier/models/classification.py:21-36`
- **Missing:** `related_ads`, `marketing_entities` (stored separately via `MarketingEntityRepository` but not part of the record).

### 23. Pipeline progress percentages are hardcoded magic numbers

- **File:** `ad_classifier/worker/stages.py:89-253`
- **Problem:** Progress values like `0.22`, `0.34`, `0.45`, `0.50`, `0.55`, `0.64`, `0.72`, `0.75`, `0.78`, `0.9` are hardcoded. These don't reflect actual stage durations and won't be accurate for different video lengths or hardware configurations.
- **Suggestion:** Track actual stage duration and report dynamic progress, or use non-numeric status indicators ("extracting frames", "running OCR").

### 24. SSE event payload uses `ad_id` of duplicate, not requested ad_id

- **File:** `ad_classifier/worker/stages.py:84-87`
- **Problem:** When an exact duplicate is detected, the emit stage name is `"dedup"` but the progress jumps to 1.0 with message `"duplicate"`. The returned `IngestArtifacts` has the existing ad's ID, not the originally requested one. The user never gets told what the original ad's ID was.

### 25. `_run_self_correction` called with list of strings but validation expects evidence_texts

- **File:** `ad_classifier/worker/stages.py:455-469`
- The `_collect_evidence_texts` returns a flat list of strings, and the correction pass receives it. But this loses the time_ms/frame_index association — the self-correction pass can't tie corrections back to specific evidence items.

---

## Dedup & Similarity Issues

### 26. `phash_distance_threshold: 4` is very tight

- **File:** `config.yaml:33`
- **Problem:** Perceptual hash hamming distance of 4 is aggressive for near-duplicate detection. Standard practice uses thresholds of 10-15. A threshold of 4 means only extremely similar frames are considered duplicates, potentially missing many true near-duplicates.
- **Suggestion:** Increase to 8-12 and test against your corpus.

### 27. `classify_verdict` doesn't use frame-level or temporal information

- **File:** `ad_classifier/dedup/verdict.py`
- **Problem:** The verdict system only compares metadata fields (brand, products, offers, subcategory) and an overall cosine score. It doesn't analyze actual frame content, scene structure, edit patterns, or other temporal ad characteristics. Two completely different ads for the same product will get "same_campaign_different_sku" even if they look nothing alike.

### 28. Similar ad enrichment re-queries the vector store inefficiently

- **File:** `ad_classifier/dedup/similarity.py:38-48, 61-69`
- **Problem:** After `store.search_text()` returns results with distances, `find_similar_by_text` immediately calls `store.get_text(found_id)` again for each result to compute a cosine score. But the search already computed distances — it's re-doing work. The vector store should ideally return distances directly from the search.

### 29. Hash-based dedup only runs at ingest, not on already stored ads

- **File:** `ad_classifier/ingest/service.py:236-271`
- **Problem:** Near-duplicate detection only checks against existing ads when a new ad is ingested. If an ad already in the DB turns out to be a near-duplicate of a later-uploaded ad, the older ad won't get a `related_ads` entry pointing to the newer one. Relation is uni-directional.

---

## NL Agent Issues

### 30. Multi-turn history omits tool results

- **File:** `ad_classifier/agent/loop.py:323-335`
- **Problem:** `_build_history()` only includes user and assistant text messages, discarding all tool_calls and tool_results from prior turns. This means on the second user question, the agent has no memory of what it just found or what queries it ran. Multi-turn conversations lose context of the database state.

### 31. `_fallback_answer_from_tool_results` overfits to tool names

- **File:** `ad_classifier/agent/loop.py:287-320`
- **Problem:** This function hardcodes specific tool names (`count_ads`, `list_ads`, `get_ad`) to build natural language fallback answers. If a new tool is added, this won't produce useful fallback text.

### 32. Tool arguments malformed check is fragile

- **File:** `ad_classifier/agent/loop.py:180-181`
- **Problem:** `if "_raw" in call.arguments and len(call.arguments) == 1:` — this assumes that a malformed tool call will have exactly one key called `_raw`. This is a brittle heuristic.

---

## Cross-Cutting Issues

### 33. Config `api_key_env` used without documenting expected env vars

- **File:** `config.yaml:66, 119`
- **Problem:** The config references `api_key_env: null` but doesn't document which environment variable name is expected. If someone sets up LM Studio with auth, there's no indication of what to set.

### 34. VLM model has separate `max_frames_in_bundle` but evidence builder passes all kept frames

- **Files:** `config.yaml:56` (`max_frames_in_bundle: 12`), `ad_classifier/pipeline/evidence/builder.py:121` (`max_frames: 12`)
- **Problem:** The frame selection algorithm works correctly, but the default of 12 frames for potentially 60+ frame ads means most frames are dropped before the VLM sees them. The selection priority order (first/last → rule triggers → OCR density → time distribution) is good, but the VLM never sees the full ad story.

### 35. `StrictModel` vs `BaseModel` inconsistency

- Some models use `StrictModel` (from `ad_classifier.models.common`), some use `BaseModel` with `extra="ignore"`. There's no consistent rule about which to use when.
- **Suggestion:** Pick one base paradigm and migrate consistently.

---

## Suggestions for Ground-Truth-First Ad Harvesting

1. **Invert the pipeline priority:** Make deterministic OCR/transcript extraction the primary source for all entities. The VLM should only categorize and structure what the deterministic layer already found — not invent new entities.

2. **Add a cross-reference validator** that, for every extracted entity, checks whether the entity's text actually appears in OCR or transcript. Reject (with a flag) any entity that has no source evidence.

3. **Track provenance at the field level:** Each extracted value should carry a `source: "ocr" | "transcript" | "vlm" | "rule"` tag and the specific frame/segment it came from. The current `evidence` list is close but not consistently populated for all entity types.

4. **Preserve all raw OCR text** and never let VLM cleanup modify it. Store corrections as a separate overlay with an audit trail.

5. **Add a "confidence in ground truth" metric** per entity based on OCR confidence, text clarity, font size, and presence in multiple frames. Low-confidence entities should be flagged in the output.

6. **Consider an OCR-text-only mode** where category classification is done solely by keyword/regex rules on OCR+transcript, bypassing the VLM entirely for classification. Use VLM only for entity structuring and relationship mapping.

7. **Add frame-level verification for every VLM claim** — if the VLM says "logo is present" or "price is $499", verify that the OCR found corresponding text in the claimed frame.

8. **Benchmark hallucination rate** by running the pipeline against known ads and comparing VLM output to OCR-only extraction. This will quantify how often the VLM fabricates content.
