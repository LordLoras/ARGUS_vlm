# Future-ingest duplicate pass: link, merge, enrich the keeper (no retroactive changes)

> Status: PLAN ONLY — nothing implemented. Existing records (including ad_0782137e / ad_936c5fb7)
> are never touched by this plan. The pass applies to future ingests only, ships in `dry_run`
> mode, and is enforced only after the demo below passes review.

## Context

`ad_0782137e` (12:30) and `ad_936c5fb7` (12:34, 2026-06-11) are the same 30s Allstate clip, both
fully processed as separate records. Why the current dedup missed them:

- Different files → different SHA256, so exact dedup couldn't fire.
- `phash_mean` Hamming distance is **3** (threshold 8), but with `skip_on_near_duplicate: false`
  the ingest near-dup check sets `DedupResult.near_duplicate_of` in memory and **persists nothing**
  (`ad_classifier/ingest/service.py:236-271`).
- Post-OCR dedup ran but `min_text_similarity: 0.9` failed because the two runs OCR'd different
  text (2610 vs 2173 paddle chars) → verdict fell below `exact_duplicate` and was only logged
  (`ad_classifier/worker/stages.py:162-166`).

**Scope decisions:**
1. **Future ingests only.** The existing pair (and all current records) are NOT touched.
   No retroactive merge command, no DB edits to current results.
2. When a future duplicate is detected: the new ad is kept, marked `duplicate_of` the original
   (earlier ad = keeper), and its data **enriches** the keeper — "more text if accurate is better".
3. Near-duplicate links are always persisted even when not merging.
4. **Nothing is applied until the demo passes** — the merge pass ships in `dry_run` mode first;
   the user reviews the logged logic, then flips one config value to enforce.

---

## The logic of the pass (decision tree for every future ingest)

```
ingest (new clip)
├─ SHA256 == existing ad        → existing behavior: skip, status=duplicate (unchanged)
├─ phash_mean within threshold  → NEW (L2 link): persist duplicate_of=resolve_keeper(match),
│                                  verdict="near_duplicate_phash", score=1-dist/64;
│                                  status stays as-is; pipeline CONTINUES
└─ frames → OCR → post-OCR dedup (find_post_ocr_duplicate):
   ├─ verdict = exact_duplicate          ┐  merge pass (if merge_mode allows):
   ├─ verdict = near_duplicate           ┘   1. keeper = resolve_keeper(match.ad_id)
   │                                         2. enrich keeper: copy OCR lines keeper lacks
   │                                            (confidence-gated, matched by frame_index),
   │                                            refresh keeper FTS row, re-embed keeper text vector
   │                                         3. mark new ad: duplicate_of=keeper, verdict, score,
   │                                            status="duplicate"; record provenance
   │                                         4. STOP pipeline → VLM call saved
   │                                       merge_mode="dry_run": log full MergeReport,
   │                                            write NOTHING, continue pipeline normally
   │                                       merging disabled for this verdict: persist link only
   │                                            (duplicate_of/verdict/score, status stays completed)
   ├─ verdict = same_campaign_different_offer → never linked, never merged (different offer!)
   └─ verdict = related                       → ignored (as today)
```

Why enrichment at this point is OCR/FTS/embedding only: at post-OCR time the new ad has no
classification or marketing entities yet, so there is nothing else to merge — and stopping before
the VLM is exactly what saves the cost. (The merge engine still supports entity-level union so the
logic is complete and testable, and a future retroactive tool could reuse it — out of scope.)

Had this existed today: the Allstate pair would have been linked at ingest by the L2 phash rule
(distance 3 ≤ 8), and the post-OCR `near_duplicate` verdict would have merged `ad_936c5fb7` into
`ad_0782137e`, copying the richer OCR text over and skipping the second VLM call.

---

## Implementation

### 1. Migration `013_ad_enrichments.sql` (provenance, additive only)

```sql
CREATE TABLE IF NOT EXISTS ad_enrichments (
  ad_id TEXT NOT NULL REFERENCES ads(id) ON DELETE CASCADE,
  source_ad_id TEXT NOT NULL,
  verdict TEXT NOT NULL,
  score REAL,
  merged_at TIMESTAMP NOT NULL DEFAULT CURRENT_TIMESTAMP,
  report_json TEXT,
  PRIMARY KEY (ad_id, source_ad_id)
);
CREATE INDEX IF NOT EXISTS idx_ad_enrichments_source ON ad_enrichments(source_ad_id);
```

Table, not a column on `ads` (`AdRecord` is StrictModel; a JSON column would need
read-modify-write across the two WAL writers). Auto-applied by `apply_migrations`
(`ad_classifier/db/connection.py:97-116`). Touches no existing rows.

### 2. Config — `PostOCRDedupConfig` (`ad_classifier/config.py:58`)

```python
merge_mode: Literal["off", "dry_run", "enforce"] = "dry_run"   # demo gate
merge_near_duplicates: bool = True        # include near_duplicate verdict in the merge set
merge_min_ocr_confidence: float = Field(default=0.75, ge=0.0, le=1.0)
```

`merge_mode="dry_run"` is the shipped default: the pass computes and logs everything, writes
nothing. Flipping to `"enforce"` in `config.yaml` activates it **after the demo passes**. Existing
`skip_on_exact` keeps its current meaning (exact verdict joins the merge set when true). Link
persistence (decision 3) applies in both dry_run and enforce. Mirror keys + comments in
`config.example.yaml` and `config.yaml`.

### 3. Shared FTS refresh — new `ad_classifier/search/fts_refresh.py`

Extract `_refresh_fts_row` from `ad_classifier/api/routes/ads.py:473` into
`refresh_fts_row(conn, ad_id, *, reuse_existing_text=True, extra_ocr_texts=())`.
**Trap:** the current code prefers existing `ads_fts.ocr_text` over recomputing —
`extra_ocr_texts` must be appended (deduped) or copied OCR would never reach FTS. The PATCH route
switches to the shared function (behavior unchanged); a new leaf module avoids import cycles.

### 4. Core engine — new `ad_classifier/dedup/merge.py` (~300 lines)

Add `MergeReport` (StrictModel) to `ad_classifier/dedup/models.py`: keeper_id, duplicate_id,
verdict, score, dry_run, already_merged, entities_merged, entity_fields_changed,
ocr_items_copied, ocr_texts_preview, campaigns_reassigned, fts_refreshed,
text_vector_refreshed, warnings.

```python
def resolve_keeper(conn, ad_id, *, max_depth=10) -> str
    # follow duplicate_of only through rows with status='duplicate' (hard dups);
    # soft-linked completed ads are legitimate keepers; cycle-guarded
def persist_duplicate_link(conn, ad_id, *, duplicate_of, verdict, score) -> None
    # update_duplicate WITHOUT status change (verified: repositories/ads.py:145
    # update_duplicate does not touch status)
def merge_duplicate_into(conn, *, keeper_id, duplicate_id, verdict, score,
                         store=None, text_embedder=None,
                         min_ocr_confidence=0.75, dry_run=False) -> MergeReport
```

`merge_duplicate_into` — no commits (caller commits), structlog with
`ad_id=keeper_id, stage="dedup:merge"`. `dry_run=True` computes every step's diff into the report
and performs **zero writes**:

1. **Guards**: both exist; `resolve_keeper(keeper_id) == keeper_id`; idempotent `already_merged`
   early-return.
2. **Entity merge** — only if the duplicate has a `marketing_entities` row (auto-detects: never
   true in the pipeline path; kept for completeness/tests). Policy: scalars fill-if-missing with
   keeper precedence (brand-name conflict → keep keeper + warning); lists union via existing
   helpers — `merge_strings`/`compact_key` (`ad_classifier/marketing/_utils.py`),
   `_dedupe_offers`/`_fuzzy_dedupe_offers`/`_fuzzy_dedupe_list`/`_dedupe_disclaimers`
   (`ad_classifier/marketing/offer_extraction.py`), `_merge_financing` (commercial.py),
   `_phone_key`/`_is_weaker_suffix_domain` (extract.py). NOT `merge_commercial_entities`
   (fill-only, not union). Evidence copied as-is — frame indices map ~1:1 (identical sampling
   cadence). Projections recomputed via `update_projection` in the same transaction (CLAUDE.md
   rule). `classifications` rows untouched.
3. **OCR copy**: duplicate `ocr_items` → keeper frames matched by `frame_index`; admit if
   `confidence IS NULL OR >= min_ocr_confidence`; skip if `compact_key(text)` already on that
   keeper frame (any engine); **preserve engine names verbatim** (consumers filter exact names:
   `ocr_cleanup` at stages.py:640, `_ocr_evidence_source`, closed `EvidenceSource` literal).
   Returns copied texts.
4. **FTS**: `refresh_fts_row(conn, keeper_id, extra_ocr_texts=copied)`;
   `fts_delete(conn, duplicate_id)` (no-op in pipeline path — dup has no FTS row yet).
5. **Re-embed keeper text**: if store + embedder given, corpus = FTS transcript_text + refreshed
   ocr_text → `store.upsert_text(keeper_id, vec)`; else warning. (Approximation of the pipeline's
   filtered corpus — documented in code.)
6. **Campaigns**: reassign duplicate's rows to keeper (`assign` upserts, then `unassign`) —
   no-op in pipeline path, complete for tests.
7. **Mark duplicate**: `update_duplicate(...)` + `update_status(dup, "duplicate")` +
   `store.delete(duplicate_id)`.
8. **Provenance**: `INSERT OR REPLACE INTO ad_enrichments` with the report dump.

### 5. Pipeline hooks — new `ad_classifier/worker/dedup_stage.py` (~120 lines)

(`stages.py` is already over the 400-line soft cap, so the logic lives in its own module.)

```python
def handle_post_ocr_duplicate(*, conn, config, ad_id, match,
                              text_embedder, emit) -> bool   # True => stop pipeline
```

- Build merge set: `{"exact_duplicate"} if skip_on_exact` ∪
  `{"near_duplicate"} if merge_near_duplicates`.
- Verdict in merge set and `merge_mode == "enforce"` → build `SqliteVecStore` + text embedder,
  `merge_duplicate_into(...)`, commit, emit `dedup:post_ocr … keeper enriched`, return True
  (VLM saved).
- Verdict in merge set and `merge_mode == "dry_run"` → `merge_duplicate_into(..., dry_run=True)`,
  log the full `MergeReport` (structlog, ad_id + stage), `persist_duplicate_link` so the pair is
  at least linked, emit `dry-run merge report logged; continuing`, return False → pipeline
  continues normally (full record still produced, nothing mutated on the keeper).
- Verdict `exact_duplicate`/`near_duplicate` outside merge set (or `merge_mode == "off"`) →
  `persist_duplicate_link` only (status stays `completed`), return False.
- `same_campaign_different_offer` / `related` → emit, return False.

**Modify `stages.py:144-166`:** replace the post-OCR block with an ~8-line delegation
(`if post_ocr_match is not None and handle_post_ocr_duplicate(...): return`).

**L2 phash link** — insert right after the dedup-skip early return (`stages.py:105`): if
`ingest.dedup.near_duplicate_of`, `persist_duplicate_link(ad_id,
duplicate_of=resolve_keeper(match), verdict="near_duplicate_phash", score=1 - distance/64)`,
committed by the existing preprocess commit. Distinct verdict string so analysts can tell phash
links from post-OCR verdicts; the post-OCR pass overwrites it with a refined verdict when it finds
a match. Only ever fires for **newly ingested** ads. Known quirk to note in a comment:
`upsert_ingest` (repositories/ads.py:29-54) nulls duplicate metadata on re-runs; the L2 step
re-persists it each run.

### 6. Count hygiene (only affects ads merged in the future)

When no `status` filter is given, append `(status IS NULL OR status <> 'duplicate')`:
- `AdRepository.list` (`ad_classifier/db/repositories/ads.py:61-140`) — explicit
  `?status=duplicate` still lists them.
- Agent tools `count_ads.py` / `list_ads.py` / `aggregate.py` (skip exclusion when
  `group_by == "status"`); one-sentence note in tool descriptions.
- Public API already defaults `status="completed"` — no change. The existing Allstate pair is
  unaffected (both `completed`).

### 7. Tests (mirror layout; no GPU/network; mock store/embedder; seeding precedent in `tests/dedup/test_post_ocr.py`)

- `tests/dedup/test_merge.py`: entity unions + dedupe keys; scalar fill + brand-conflict warning;
  confidence gating; OCR copy by frame_index + per-frame dedupe + engine preserved; FTS keeper
  grew / dup row gone; campaign reassign; dup marking; mock store calls; embedder-None warning;
  provenance row; **dry-run leaves DB byte-identical**; re-merge → `already_merged`;
  `resolve_keeper` chain/depth/cycle/soft-link-not-chased.
- `tests/worker/test_dedup_stage.py`: parametrized verdict × `merge_mode` × flags →
  enforce-merge/stop vs dry-run-log/continue vs link-only/continue vs ignore; dry-run persists
  link but mutates nothing else; L2 `near_duplicate_phash` link with canonicalized target.
- `tests/search/test_fts_refresh.py`: reuse vs recompute vs `extra_ocr_texts`.
- Extend agent tool + repo/API list tests for the default `status<>'duplicate'` exclusion.

### 8. Docs

`config.example.yaml` comments (esp. `merge_mode` lifecycle: dry_run → review logs → enforce);
one clause in AGENTS.md dedup description; CLAUDE.md untouched (no CLI surface changes in this
phase).

---

## Demo gate (nothing enforced until this passes)

1. `python -m pytest tests/ -q` + `ruff check` / `black --check` / `mypy` — the decision-tree
   tests ARE the logic spec, reviewable in `tests/worker/test_dedup_stage.py`.
2. Live dry-run demo with the worker running and `merge_mode: dry_run` (default):
   ```powershell
   ffmpeg -i data\uploads\ad_936c5fb7.mp4 -c:v libx264 -crf 24 demo_dup.mp4   # new SHA256, same clip
   # upload demo_dup.mp4 via the UI or POST /ads/upload
   ```
   Expected in the worker log: L2 `near_duplicate_phash` link persisted at ingest; at
   `dedup:post_ocr` a full dry-run `MergeReport` (keeper id, verdict, score, OCR lines that would
   be copied, FTS delta, "would mark duplicate"), then the pipeline continues and produces a
   normal record. **Keeper `ad_0782137e`/`ad_936c5fb7` rows remain byte-identical** (spot-check
   with read-only sqlite).
3. User reviews the logged pass logic. Cleanup: delete the demo ad via the existing
   `DELETE /ads/{id}`.
4. Only after approval: set `dedup.post_ocr.merge_mode: enforce` in `config.yaml`
   (one-line change, separate commit).

## Explicit non-goals (this phase)

- No retroactive merge of `ad_0782137e` / `ad_936c5fb7` (or any existing records); no
  `merge-duplicates` CLI. The merge engine is reusable if a retroactive tool is wanted later.
- No frontend changes (duplicate fields already flow through `AdRecord`; `RelatedTab` verdict
  labels should fall through gracefully for `near_duplicate_phash` — verify visually during demo).

## Risks

- False-positive near-dup merge would skip the VLM for the new ad — mitigated by post-OCR's own
  gates (≥0.90 frame match etc.), `same_campaign_different_offer` never merging, the dry-run demo
  gate, and the kept (not deleted) duplicate record as recovery.
- Merge-time re-embed uses the DB/FTS-derived corpus, not the pipeline's overlay/fine-print
  filtered one — slight score drift on enriched keepers; documented in code.
- WAL write contention worker-vs-API during merges is bounded: merge runs inside the worker's
  existing connection/commit discipline.

## Verified facts the plan relies on (re-check before implementing)

- `PostOCRDedupConfig` at `ad_classifier/config.py:58`; note `DedupConfig.phash_distance_threshold`
  default in code is 4 — `config.yaml` overrides it to 8.
- Post-OCR verdicts (`exact_duplicate` / `near_duplicate` / `same_campaign_different_offer` /
  `related`) in `ad_classifier/dedup/models.py:9-14`; `PostOCRDuplicateMatch` carries
  `overall_score` + component similarities.
- `AdRepository.update_duplicate` (`repositories/ads.py:145`) does NOT touch `status`;
  `update_status` is separate — link persistence needs no new repo method.
- The post-OCR candidate query already filters `duplicate_of IS NULL AND status='completed'`
  (`dedup/post_ocr.py:105-114`), so its matches are merge roots by construction.
- Existing migrations end at `012_job_stage.sql` → next is 013.
- Merge helpers exist: `merge_strings`/`compact_key` (`marketing/_utils.py`), `_dedupe_offers`
  (`marketing/offer_extraction.py:396`), `MarketingEntities` (`models/marketing.py:194`).
- Both ads currently: status `completed`, null duplicate columns, full FTS rows, text + visual +
  per-frame vectors (48/49), no campaign memberships.
