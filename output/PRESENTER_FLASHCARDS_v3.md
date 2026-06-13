# ARGUS presenter flash cards — deck v3

Deck A matches `ARGUS_Demo_Deck_v3.pptx` (16 slides) slide-for-slide. Cycle these:
read **Q**, answer out loud, flip to **A**. Decks: A = the talk, B = access
boundaries, C = storage & artifacts, D = numbers, E = hard questions, F = tech-stack
glossary. Cards are self-contained — learn any deck independently.

---

## Deck A — the talk, slide by slide

**A1 — Q: What is ARGUS in one sentence?**

**A:** It watches TV ads the way an analyst would — looks at frames, listens to audio,
reads the fine print — and turns each ad into a structured, searchable record you can
question in plain English.

---

**A2 — Q: What's the problem? (slide 2)**

**A:**
- A TV ad is 30 seconds of information that *disappears* — a price flashes for 2s.
- Watching doesn't scale: hundreds of creatives, human eyes, inconsistent.
- Answers need proof: "which ads promised 0% APR?" deserves the exact frame as receipt.

---

**A3 — Q: What is ARGUS — the four functions? (slide 3)**

**A:** Two main, two side — same layout as the app's menus, same order as the demo.
- **MAIN 1 · The Library** — TV ads ingested manually, each turned into a complete,
  searchable record: brand, offer, fine print, every word, every frame.
- **MAIN 2 · The Crawler** — learns brands & products from the open web *before*
  their ads air. Say it: *the highest-payoff piece — I'll spend the most time there.*
- **SIDE 1 · The Agent** — plain-English questions over the library; every answer
  cites its ads.
- **SIDE 2 · The Creative Panel** — six simulated viewers critique an ad using only
  its real evidence.

---

**A4 — Q: Walk the library pipeline. (slide 4)**

**A:** Five steps, left to right: video → **ingest** (snapshots & words) → **dedup**
(seen before?) → **fine print** (prices & disclaimers) → **AI verify** (brand,
product, offer) → **search** (find anything, by meaning). Every fact keeps the frame
and moment it came from. The next slides walk the steps with real examples.

---

**A5 — Q: What does ingest produce, and why? (slide 5)**

**A:**
- Why: a model can't watch video, and neither can a search box.
- A snapshot every 0.5s (~60 per 30s spot), clean mono audio, every spoken word.
- Everything timestamped — every later claim points to a replayable moment.
- Under the hood: ffmpeg sampling + Whisper transcription → chronological manifest.

---

**A6 — Q: What's in one library record? (slide 6)**

**A:** Brand & products, category & IAB taxonomy, offers & fine print, full transcript
+ on-screen text, every frame, confidence & history. Habit to repeat: *click any fact
and you land on the frame and moment behind it.*

---

**A7 — Q: The four dedup layers + the Jeep story. (slide 7)**

**A:**
- L1 exact file fingerprint → L2 near (re-encoded creative) → L3 offer-aware (same
  footage, different APR) → L4 semantic (related by meaning; enriches, never merges).
- Jeep: five ads share footage, push different lease offers — kept separate, linked
  as one campaign. Naive systems merge them or miss the link; ARGUS does neither.

---

**A8 — Q: Why does fine print come before AI? (slide 8)**

**A:**
- The most commercially important text is on screen: prices, APR, disclaimers, phones.
- Captured deterministically — the paper trail every AI answer is checked against.
- Demo fact: "$149/month · 36-month lease" at **0:06.5** — word, place, moment.
- Under the hood: PaddleOCR with boxes + confidence; dense frames escalate to a second
  vision-OCR pass; **raw OCR is never overwritten**.

---

**A9 — Q: How does AI verification stay honest? (slide 9)**

**A:**
- Fixed evidence packet in, strict JSON out — no free association.
- Must cite timestamps; a deterministic checker compares output to observed OCR.
- Anything it can't point to in a frame or transcript is **dropped**.
- Example: RAV4 spot → automotive · SUV · Toyota · "Let's go places."

---

**A10 — Q: What makes search the crowd-pleaser? (slide 10)**

**A:**
- You remember what an ad *looked like*, not its words: `red car`, `small disclaimer`.
- ARGUS stored what every frame looks like — finds the exact frame, not just the ad.
- One box fuses keywords + text meaning + visuals into a single ranked result.

---

**A11 — Q: The crawler's big idea. (slide 11)**

**A:**
- **TV is the slow signal; the web is the fast one.** A product page goes live weeks
  before the campaign airs — so ARGUS learns from the web first.
- A living map of brands & products — who makes what, who owns whom — built outward
  from the ads in the library (88 entities · 165 connections).
- Real example: iPhone 17 Pro and T-Mobile's T-Satellite entered the graph from the
  open web — recognized the day their next ad airs.

---

**A12 — Q: How does the crawler avoid making things up? (slide 12)**

**A:**
- **Dual search:** search-engine APIs aggregate what's out there, then ARGUS visits
  the websites themselves to verify and extract.
- Anchored in the ads: starts at the advertiser's own site, walks outward — product
  pages, manufacturer catalog, related brands met with confidence.
- **The web is a signal, never proof** — every web fact stays a candidate until
  corroborated.
- Under the hood: Playwright renders JS-heavy pages, a vision model verifies every
  page it reads.

---

**A13 — Q: The four roadmap items — and the framing rule. (slide 13)**

**A:** Chain search (discoveries queue their own crawls) · deeper catalog crawls ·
scheduled re-crawls · upload assist (new ads arrive already understood — recognized
on day one). FRAMING RULE: these are **planned, not shipped** — say "where it's
heading."

---

**A14 — Q: The agent's pitch and its trust line. (slide 14)**

**A:**
- Ask: "Which brands used urgency tactics this quarter?" — answer in seconds.
- Every answer cites the actual ads behind it — click through and check.
- Trust line out loud: *it sees everything and changes nothing — enforced by the
  database itself, not a polite instruction.*

---

**A15 — Q: Creative panel — pitch + mandatory caveat. (slide 15)**

**A:**
- Six personas (budget parent, skeptical checker, luxury shopper, first-time buyer,
  Gen-Z viewer, compliance reviewer) argue about the ad.
- They may only argue about what's *in* the ad: real transcript, real text, real offer.
- SAY THE CAVEAT: **a simulation, not a focus group** — fast repeatable critique,
  not market research.

---

**A16 — Q: The close. (slide 16)**

**A:** "It watches, reads, and listens — so you can just ask." Then switch to the live
system at `127.0.0.1:5173` and walk it in the same order: library, crawler, agent,
creative panel.

---

**A17 — Q: The three habits. (bonus — no longer its own slide in v3, still true)**

**A:** Weave in if asked about design principles:
1. **Evidence first, AI verifies** — deterministic reading first; AI must cite timestamps.
2. **Everything traceable** — every fact links to the exact frame or spoken word.
3. **Machine proposes, people decide** — groupings/corrections only stick when accepted.

---

## Deck B — access boundaries (who can touch what)

**B1 — Q: What can the AGENT access?**

**A:**
- **Reads:** the entire main DB (`ad_classifier.db`) — but the connection is opened
  with `PRAGMA query_only=ON`, so SQLite itself refuses writes.
- **Through tools only:** 10 fixed tools — list/count/get ads, campaigns, aggregate,
  hybrid search, vector similarity, compare ads, plus a `sql_readonly` escape hatch
  capped at 50 rows. Vectors are queried inside the DB; the agent sees result rows
  and citations, never raw embeddings.
- **Writes:** nothing. Its audit trail (`agent_sessions`, `agent_messages`) is
  written by the host loop, not by any tool the model can call.
- **Network:** only the configured LLM endpoint.

---

**B2 — Q: What can the CREATIVE DEBATE access?**

**A:**
- **Reads exactly five things, for one ad:** the `ads` row, `classifications`,
  `marketing_entities`, `transcript_segments`, `ocr_items`. It cannot browse the
  library or other ads.
- **Writes:** zero database rows. Output is a JSON report only:
  `data/out/{ad_id}/creative_debate.json` (and `creative_panel.json`).
- **Two engines:** deterministic fallback (free, instant, no model) and VLM mode
  (one structured call per persona; failures fall back per-persona and the report
  labels itself `vlm_with_fallback`).
- Every report embeds the caveat: simulated, not a focus group.

---

**B3 — Q: What can the CRAWLER / ENTITY GRAPH access?**

**A:**
- **Reads (main DB, read-only repo):** almost entirely *metadata* — `ads` projection
  columns (brand, advertiser, products, category, IAB, website/landing domains) plus
  the `marketing_entities` JSON (brand/products/advertiser/contact/landing-page).
  That metadata is the fuel for product candidates, web targets, and search queries.
- **OCR + transcript: provenance only.** One targeted lookup per product finds the
  best `ocr_items`/`transcript_segments` line mentioning it — to anchor the
  observation to a frame/timestamp and set confidence (0.88 grounded vs 0.52 not).
  Never read as bulk content.
- **Never touched:** frame images, visual vectors, whisper files on disk. The
  crawler's VLM looks at web pages, never ad frames.
- **Reads:** `knowledge.db` (IAB taxonomy reference), `entity_crawler.yaml` (policy).
- **Writes:** only `entity_graph.db` — nodes, edges, observations, crawl runs,
  suggestions — plus its page cache in `data/entity_crawler_cache/`.
- **Network:** the only module with open-web access — DuckDuckGo HTML + entity
  pages; robots.txt respected, 30 req/min, Playwright fallback, VLM page verifier.

---

**B4 — Q: The ONE exception to crawler isolation?**

**A:** Approved **ad change suggestions**. To touch the main DB, a suggestion must be
(1) enabled in `entity_crawler.yaml`, (2) explicitly approved by a human, and
(3) target one of **four whitelisted columns**: `brand_name`, `products_text`,
`primary_category`, `subcategory`. Anything else raises a permission error.
Volunteer this before someone finds it — it's stronger than claiming "fully read-only."

---

**B5 — Q: Who is allowed to WRITE the main DB at all?**

**A:** Only the pipeline worker and the API (uploads, campaign accepts, settings).
Agent: read-only by pragma. Debate: file output only. Crawler: own DB + the
human-gated four-column repair. Plus one network footnote: **brand enrichment**
(on-demand Wikipedia/Wikidata profiles) is the single submitted-side feature that
touches the internet — analyst-triggered, never automatic.

---

## Deck C — storage & artifacts (what lives where)

**C1 — Q: What persistent artifacts does one ad leave on disk?**

**A:**
- `data/uploads/` — the original video.
- `data/frames/{ad_id}/` — sampled frame JPGs (~60 for a 30s spot).
- `data/audio/` — extracted mono 16 kHz track.
- `data/whisper/{ad_id}/whisper.json` + `whisper.raw.json` — transcript artifacts.
- `data/out/{ad_id}/manifest.json` — chronological frame/transcript manifest.
- `data/out/{ad_id}/raw_ocr_items.json` — raw OCR snapshot (before any cleanup).
- `data/out/{ad_id}/creative_panel.json` / `creative_debate.json` — persona reports.
- Cached artifacts = restartability: a re-run reuses whatever already exists.

---

**C2 — Q: Where do the vectors live?**

**A:** In **the same SQLite file** as everything else (`ad_classifier.db`), in
`sqlite-vec` virtual tables — not JSON, not a separate vector DB. One file holds the
rows, the FTS5 index, and the vectors. (Qdrant exists in config as a future backend;
the running path is sqlite-vec.)

---

**C3 — Q: What runs on what — MiniLM vs SigLIP?**

**A:**
- **MiniLM** (`all-MiniLM-L6-v2`, 384-dim): **text only** — one ad-level vector from
  concatenated transcript + searchable OCR text. It never sees frames.
- **SigLIP 2** (`siglip2-base-patch16-224`, 768-dim): **frames** — one vector per
  *kept* keyframe (variable count per ad) plus a mean-pooled ad-level vector.
  Shared text/image space is what makes typed visual queries (`red car`) work.

---

**C4 — Q: The frame funnel — how many frames where? (real ad: 30s Toyota)**

**A:** **60 sampled → 33 kept → ≤12 to the VLM.**
- 60 sampled (one per 500ms, `frame_interval_ms`), all saved as JPGs.
- **33 is not a setting** — it's what survives the retention ladder: first/last
  always kept; blank dropped (gray std-dev < 10); blurry dropped (Laplacian < 100);
  near-dup dropped (pHash hamming < 8 AND pixel diff < 5% vs previous kept frame).
  Toyota ad's 27 drops: 17 blurry, 10 near-dup, 0 blank. Kept frames get OCR +
  one SigLIP vector each (+1 mean-pooled ad vector); 738 frame vectors library-wide.
- **12 is a setting** (`vlm.max_frames_in_bundle`). Selection ladder when kept > 12:
  first + last → rule-trigger frames by severity → highest OCR density →
  time-distributed fill; frame-index tie-breaks. Deterministic — same ad, same 12.
- Why the asymmetry: the VLM is expensive → give it the densest evidence; search
  needs coverage → every kept frame stays searchable. Visual search can return a
  frame the classifier never saw.

---

**C5 — Q: JSON vs projection columns — which is the truth?**

**A:** The JSON in `classifications` and `marketing_entities` is the **source of
truth**. Projection columns on `ads` (`brand_name`, `products_text`,
`primary_category`, IAB columns) are convenience copies written **in the same
transaction** so list views and filters stay fast. WAL mode lets API and worker
use the one file concurrently.

---

**C6 — Q: What is each of the three vector types USED for?**

**A:**
- **Text ad vector** (MiniLM, 384, one per ad): semantic text search; the vector
  half of hybrid search (fused with keyword FTS via reciprocal rank fusion); the
  text-similarity score in related-ads; the agent's `vector_similarity` tool.
- **Ad-level visual vector** (SigLIP, 768, mean-pooled from kept frames): whole-ad
  visual similarity — the visual score in related-ads, and campaign discovery in
  two roles: clustering input for brand-scoped visual groups, AND a coherence gate
  even for name-based groups (a repeated VLM-extracted campaign name still needs
  the ads to pass `min_mean_similarity` visually; raw OCR is never re-read at
  discovery time — offers only name the campaign, never decide membership).
- **Per-frame visual vectors** (SigLIP, 768 × each kept frame): typed visual search
  (`red car`, `small disclaimer`) — the query text is embedded into the same SigLIP
  space and the *best cosine per ad* wins, so results point at the exact frame. An
  ad survives if ANY keyframe clears the bar; the mean-pooled vector alone would
  dilute a one-frame match.

---

**C7 — Q: How are inputs picked and sent to MiniLM, SigLIP, and the VLM?**

**A:**
- **MiniLM — no frames at all.** One string per ad: full transcript + all searchable
  OCR text (incl. GLM-OCR when search-enabled), embedded once → one 384-dim vector.
- **SigLIP — every kept frame, no further selection.** Batch-embeds the kept-frame
  JPGs (all 33 in the sample ad) → one vector each, then mean-pools the ad vector.
- **VLM — the only place frames are *chosen*.** If kept ≤ 12, all go. Otherwise a
  deterministic ladder fills 12 slots: (1) first + last frame, (2) rule-trigger
  frames by severity, (3) highest OCR-density frames, (4) time-distributed fill —
  frame-index tie-breaks, fully reproducible, no randomness.
- **How the VLM receives it:** one message — the full text evidence first
  (per-frame `[Frame N @ Tms]` segments with OCR/transcript), then the selected
  images appended in chronological order (downscaled, base64).

---

## Deck D — numbers

**D1 — Q: Library and campaign numbers?**

**A:** **28 ads** in the demo library · **5 Jeep ads** = one campaign
("Declaration of Deals") · ~**60 snapshots** per 30s spot (every 0.5s) ·
pipeline time **~2.5 min median per ad** (45s–6.5min across all 28 jobs).

---

**D2 — Q: Graph numbers?**

**A:** **88 entities · 165 connections** · candidates stay separate from confirmed ·
iPhone 17 Pro + T-Satellite arrived from the web.

---

**D3 — Q: Benchmark numbers — and the safe phrasing?**

**A:** 11 routes × 5 ads, all 5/5. **Gemma 4 31B: 93.16** · GPT-5.5: 92.38 ·
margin **0.78 ≈ noise**. Gemma is also slowest (~281s vs 43s).
Safe phrasing: *"Gemma matches frontier routes on our rubric while being
local-friendly"* — not "Gemma beats them."

---

**D4 — Q: Guardrail numbers?**

**A:** Agent: **10 tools**, SQL capped at **50 rows**. Crawler repairs: **4
whitelisted fields**, human-approved. Crawler etiquette: **30 req/min**, robots.txt.
Embeddings: **384-dim** text, **768-dim** visual.

---

## Deck E — hard questions

**E1 — Q: "Does any model actually watch the video?"**

**A:** No. Every model receives frames already ordered and timestamped by the
pipeline. Temporal grounding is the *pipeline's* job — models compete on reasoning
over evidence, not on perception. That's deliberate design.

---

**E2 — Q: "Why is Gemma top of the benchmark?"**

**A:** Extraction accuracy and format discipline on our rubric — and the margin is
0.78 points across five ads, which is noise. The rubric doesn't directly measure
temporal reasoning, so don't attribute the lead to it. An ablation (shuffled frame
order) is designed but not yet run.

---

**E3 — Q: "Is the crawler autonomous? Could it poison the data?"**

**A:** Discovered entities become **candidates** — they can't pollute the confirmed
graph without corroboration or review. In-run link-following is capped per page.
Fully automatic chain search is roadmap. And the main ad database is behind a
read-only window plus a four-field, human-approved repair path.

---

**E4 — Q: "What stops the AI from inventing a price or a brand?"**

**A:** A deterministic checker validates VLM output against observed OCR before
saving; ungrounded claims are dropped. Raw OCR is never overwritten, so there's
always an immutable paper trail to re-check against.

---

**E5 — Q: "Is this content moderation / censorship?"**

**A:** No — categorization only. Risk labels are descriptive observation tags for
analysts ("show me ads using urgency tactics"); nothing gates, blocks, escalates,
or goes to a review queue. There are no thresholds anywhere.

---

**E6 — Q: "What does it cost / where does it run?"**

**A:** Local-first: one machine, one SQLite file, local OCR/Whisper/embeddings.
The only paid call is the VLM endpoint — and the benchmark page shows measured
score-per-dollar across routes, including a local Gemma that needs no API at all.

---

**E7 — Q: "How accurate is it?"**

**A:** Honest framing: there's no large labeled evaluation set yet — the benchmark
is a 5-ad reference rubric built to *compare model routes*, not an accuracy
certificate. The design answer matters more: every output is **checkable** —
category, entities, and claims cite frames and timestamps, ungrounded claims are
dropped before saving, and raw OCR is never overwritten. Wrong answers don't hide;
they're one click from their evidence. A larger labeled eval set is the natural
next step.

---

**E8 — Q: "What data leaves the machine?"**

**A:** Depends on the VLM route, and say it plainly:
- **Frontier mode (current demo):** the evidence bundle — up to 12 downscaled
  frames + OCR/transcript text — goes to the configured endpoint (OpenRouter) per
  ad. Same for agent/debate/research prompts.
- **Fully local mode:** nothing leaves — the benchmark's local Gemma row proves
  the pipeline works 100% on-box.
- Always local: the videos, the database, all artifacts, all vectors.
- Outbound by design: the crawler (open web) and on-demand brand enrichment
  (Wikipedia/Wikidata). Neither sends ad content out — they only fetch.

---

**E9 — Q: "How long does one ad take?"**

**A:** **Median ~2.5 minutes** end-to-end (45 seconds to 6.5 minutes across all 28
library jobs), dominated by the VLM call and transcription. Stages cache their
artifacts, so a re-run only pays for what changed. Processing is a background job
with live progress streaming — you upload and watch it move.

---

**E10 — Q: "Why not just hand the whole video to GPT/Gemini?"**

**A:** The founding design decision. Four reasons:
1. **Auditability** — a single model answer can't show its work; ARGUS builds the
   evidence first and makes the model cite it.
2. **Determinism** — OCR, rules, hashes, and frame selection are reproducible;
   model output is validated against them.
3. **Cost** — 12 selected frames + text per ad instead of full video tokens, and
   the deterministic layers run free and locally.
4. **Independence** — any OpenAI-compatible model can be swapped in; the benchmark
   page exists precisely because the pipeline doesn't marry one model.

---

**E11 — Q: "Why SQLite and not Postgres + a vector database?"**

**A:** Local-first with zero infrastructure: one file holds rows, full-text index
(FTS5), and vectors (sqlite-vec) — no servers to install, back up, or keep running.
WAL mode gives the needed concurrency (one worker + API). At this scale, in-process
search beats network hops. If volume ever demands it, the config already carries a
Qdrant backend stub and the graph schema is deliberately portable.

---

**E12 — Q: "What happens if it crashes mid-job?"**

**A:** Every stage caches its artifacts (frames, audio, transcript, OCR, manifest),
so a restart reuses everything already done and only the failed stage and its
downstream re-run. Interrupted jobs are requeued automatically at startup
(`recover-jobs`, built into start.bat). Failures mark the job with a short
user-facing error; full tracebacks go to logs, never to the API.

---

**E13 — Q: "Does it work in other languages?"**

**A:** Built and tested English-first: the bundled Whisper model is English-only,
PaddleOCR is configured for English, and the rules/taxonomy are English. The
components themselves are multilingual-capable (Whisper auto-detect, PaddleOCR
language packs, SigLIP multilingual training) — so other languages are a
configuration exercise plus testing, not a redesign.

---

**E14 — Q: "What if Whisper mishears something?"**

**A:** It does — the config notes the bundled tiny model can hear "Jeep" as
"cheap." Three mitigations: (1) swapping to a larger Whisper model is one config
line; (2) the transcript is only one of several evidence sources — OCR and frames
cross-check it, and the VLM reports conflicts; (3) prices, APR, and legal terms are
anchored to *on-screen* text, never to audio alone.

---

**E15 — Q: "What are the 'rules' in the rules engine, actually?"**

**A:** YAML-configured keyword/regex patterns over OCR + transcript — each with a
category or risk label, a severity, and the matched evidence text + timestamp.
Deterministic and auditable: an analyst can add one without retraining anything.
They also steer the pipeline — rule-trigger frames get priority seats in the VLM's
12-frame bundle.

---

**E16 — Q: "Why can a short visual search like `crab boat` return unrelated ads?"**

**A:** Visual search is **not an LLM prompt** and not exact word matching. The query
is embedded once with SigLIP, then ARGUS searches every kept frame vector for nearest
visual neighbors. Short phrases are broad: `crab boat` finds Discovery first, but weak
visual neighbors can survive because the visual threshold is intentionally permissive
for exploration. Longer, concrete phrases work better because they anchor scene +
object + visible text — e.g. `tv show weathered paper note next friday fishing boat`.
Words like `tv show`, `lawyer`, `car`, and `truck` also trigger intent filters that
drop unrelated categories. If the user wants literal `red car`, that needs object/color
grounding (YOLO-style detection + color inside the car box); SigLIP alone is semantic
similarity, not a detector.

---

## Deck F — tech-stack glossary (if someone asks "what is X?")

**F1 — Q: What is FTS5?**

**A:** SQLite's built-in full-text search engine. It keeps an inverted index of every
word (which words appear in which ad, like a book index) and ranks matches with BM25 —
rewarding rare, specific terms over common ones. It's ARGUS's keyword search: brands,
phone numbers, exact offer phrases. Zero extra infrastructure — it's a table in the
same database file.

---

**F2 — Q: What is sqlite-vec?**

**A:** An SQLite extension that stores embedding vectors and does similarity search
inside the database itself — the job people usually run a separate vector DB
(Pinecone, Qdrant) for. ARGUS keeps all 700+ vectors in the same file as the rows
and the text index. One file, three kinds of search.

---

**F3 — Q: What is WAL mode?**

**A:** Write-Ahead Logging — an SQLite journaling mode where writes go to a separate
log file before merging into the main database. The practical win: readers don't
block the writer, so the API can serve the UI while the worker is mid-pipeline on
the same file. It's why ARGUS needs no database server.

---

**F4 — Q: What is an embedding / a vector?**

**A:** A list of numbers (384 or 768 here) that captures the *meaning* of text or the
*look* of an image, produced by a neural network. Similar things land near each other,
so "find similar" becomes geometry: measure the angle between two vectors (cosine
similarity). It's how ARGUS searches by meaning instead of exact words.

---

**F5 — Q: What is RRF (reciprocal rank fusion)?**

**A:** A way to merge ranked lists from different search engines without comparing
their incompatible scores. Each result earns points based on its *rank* in each list
(1/(k + rank)), and the points are summed. Something ranked well by both keyword and
vector search beats a winner from only one. It's how hybrid search fuses FTS5 + vectors.

---

**F6 — Q: What is MiniLM?**

**A:** `all-MiniLM-L6-v2` — a small, fast sentence-transformer that turns text into a
384-dim meaning vector. Tiny by today's standards (~22M parameters), runs locally in
milliseconds, and is a well-tested default for semantic text search. ARGUS feeds it
transcript + OCR text, one vector per ad.

---

**F7 — Q: What is SigLIP 2? Why not CLIP?**

**A:** Google's image-text embedding model: images and text map into the *same*
vector space, so the text `red car` can be compared directly against frame images.
Same family as CLIP but trained with a sigmoid loss — better fine-grained
discrimination and notably better at text *inside* images, which matters when frames
are full of on-screen offers. The interface is model-agnostic; CLIP variants can be
swapped in by config.

---

**F8 — Q: What is PaddleOCR?**

**A:** An open-source OCR engine (Baidu's PaddlePaddle ecosystem) that detects text
regions and reads them — returning the text, a bounding box, and a confidence per
item. Runs locally on CPU. ARGUS uses it as the *grounded* OCR source: its raw
output is never overwritten.

---

**F9 — Q: What is Whisper / whisper.cpp?**

**A:** Whisper is OpenAI's open-source speech-to-text model; whisper.cpp is a fast
C++ port that runs it locally without Python or a GPU framework. ARGUS bundles the
CLI plus a small English model for transcripts with per-segment timestamps; swapping
to a larger model is one config line.

---

**F10 — Q: What is a pHash / Hamming distance / Laplacian variance?**

**A:** The image math behind frame filtering and dedup, all deterministic:
- **pHash** (perceptual hash): a 64-bit visual fingerprint that survives re-encoding
  and compression — similar images get similar hashes.
- **Hamming distance**: how many bits differ between two hashes (< 8 ≈ same image).
- **Laplacian variance**: an edge-sharpness score — blurry frames have soft edges,
  low variance (< 100 → dropped).

---

**F11 — Q: What is a VLM / "OpenAI-compatible endpoint"?**

**A:** A vision-language model — an LLM that accepts images alongside text.
"OpenAI-compatible" means the server speaks the de-facto standard chat API, so ARGUS
can point at LM Studio on localhost, a self-hosted server, or OpenRouter (one API
key, many frontier models) by changing one config block. That's how the benchmark
tests 11 routes with the same code.

---

**F12 — Q: What are FastAPI / SSE / Pydantic?**

**A:**
- **FastAPI**: the Python web framework serving the JSON API — typed, async, and it
  auto-generates the OpenAPI docs the frontend's client is generated from.
- **SSE** (server-sent events): one-way live streaming over plain HTTP — how job
  progress and agent responses stream into the UI without WebSockets.
- **Pydantic**: typed, validated data models — every pipeline stage exchanges
  validated objects, and the VLM's JSON is parsed against a strict schema.

---

**F13 — Q: What is Playwright?**

**A:** A browser-automation library — it drives a real headless Chromium. The crawler
escalates to it when plain HTTP returns thin or blocked content (JavaScript-rendered
product pages, anti-bot walls), and it can hand a page *screenshot* to the VLM for
verification.

---

**F14 — Q: What is the IAB taxonomy?**

**A:** The ad industry's standard category trees (Interactive Advertising Bureau).
ARGUS maps each ad to IAB **Product Taxonomy 2.0** (what's being sold) and **Content
Taxonomy 3.1** (what the content is about), choosing the deepest tier the evidence
supports, with confidence. Standard IDs mean exports line up with industry tools
instead of a homegrown category list.

---

**F15 — Q: Tool-calling vs text-to-SQL — what's the difference and why does it matter?**

**A:** Text-to-SQL lets a model write raw SQL — flexible, but you're trusting
generated queries. Tool-calling gives the model a fixed menu of named operations with
typed arguments; each maps to a parameterized query template. ARGUS's agent is
tool-calling: predictable, auditable, injection-resistant — and the bounded
`sql_readonly` escape hatch exists for the long tail, capped and logged.
