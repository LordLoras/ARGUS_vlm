# ARGUS Demo Feature Roadmap

Last updated: 2026-05-18

This is a clean-slate feature list for demo-worthy ARGUS roadmap ideas. Already-built features are intentionally not tracked here. The existing local agent, creative review panel, debate panel, campaign pages, hybrid search, visual search, deduplication, and base extraction pipeline are treated as platform primitives.

## Guardrails

- Keep ARGUS categorization-only. No approve, block, flag, escalation, or review-queue workflow.
- Keep risk labels as descriptive observation tags for analysis and search.
- Do not present synthetic personas as real consumers, representative samples, or market forecasts.
- Ground generated outputs in persisted evidence whenever possible: frames, OCR, transcript, entities, rules, classifications, embeddings, and campaigns.
- Local-first remains the default. Any optional cloud/frontier model mode must sit behind the same model interfaces and have deterministic or mock fallback.
- Do not revive director-shot-list reconstruction as a standalone feature. The demo should focus on searchable creative intelligence, analysis, generation, and evidence-backed strategy artifacts.

## Research Signals Used

These are directional signals for feature design, not hard dependencies:

- Promptable video segmentation and tracking are now practical enough to build object-level video intelligence flows, especially with SAM 2 style models.
- Modern video-capable VLMs can describe, segment, extract information from video, answer timestamped questions, and reason over long clips.
- Video moment retrieval research supports frame/segment-level search rather than only whole-ad retrieval.
- Video emotion and affective analysis remains useful for advertising effectiveness exploration, but ARGUS should frame it as structural/emotional cues, not true viewer emotion.
- Generative AI is now a major advertising workflow, so demo features should include generation, transformation, and packaging, not only passive analysis.

## Demo Priority Stack

Build these first if the goal is maximum demo impact:

1. Multimodal Moment Search 2.0
2. Creative DNA Genome
3. Hook and Payoff Timeline
4. Competitive White-Space Map
5. Claim Grounding Graph
6. Object Track and Brand Presence Graph
7. Counterfactual Creative Lab
8. Auto Strategy Deck Generator
9. Campaign Drift Radar
10. Generative Variant Factory

---

# 10 Heavy AI Research Features

These are the highest-wattage AI features. They use computer vision, VLM reasoning, embeddings, speech/audio models, graph construction, generative models, or model evaluation loops.

## 1. Multimodal Moment Search 2.0

Let analysts search for exact moments inside ads, not just ad records.

Demo prompt examples:

- "Show me every frame where a price appears before the product is named."
- "Find product close-ups with voiceover but no on-screen CTA."
- "Find red vehicle shots that mention APR within 2 seconds."

AI stack:

- Frame visual embeddings
- OCR and transcript alignment
- VLM reranker for ambiguous moments
- Temporal fusion scoring
- Optional shot boundary detection

MVP:

- Add `/api/moments/search`.
- Return `ad_id`, `frame_index`, `time_ms`, thumbnail, OCR snippet, transcript snippet, and score.
- Add a Moment Search page with timestamp cards and a mini timeline.

Demo punch:

- The user searches a concept and gets the exact proof frame, not a generic ad list.

## 2. Creative DNA Genome

Generate a compact creative profile for each ad: hook type, emotional posture, pacing, product clarity, proof style, offer mechanics, brand density, CTA type, visual density, and final payoff.

AI stack:

- VLM temporal reasoning
- Entity extraction
- Embedding-derived similarity
- Rule-based timing features
- LLM summarization with JSON schema

MVP:

- Add `ad_classifier/creative/dna/creative_dna.py`.
- Persist `creative_dna.json` under `data/out/{ad_id}/`.
- Add a drawer tab with a genome radar, beat chips, and comparable ads.

Demo punch:

- "This Jeep ad is offer-first, proof-light, brand-late, CTA-explicit, high-motion."

## 3. Object Track and Brand Presence Graph

Track products, people, logos, text blocks, end cards, QR codes, and major objects across frames, then show when each appears and disappears.

AI stack:

- Promptable video segmentation
- Object detection
- Logo detection or visual exemplar matching
- OCR box tracking
- Temporal graph construction

MVP:

- Start with OCR box tracking and simple object labels from keyframes.
- Later add SAM-style promptable tracking for product/logo masks.
- UI: horizontal tracks for product, logo, price, CTA, person, phone, URL.

Demo punch:

- "Brand logo appears only in the last 2.5 seconds; price appears 4 times; CTA appears once."

## 4. Neural Attention and Readability Heatmap

Create a proxy heatmap for likely visual attention and text readability. This is not eye tracking; it is an AI/readability heuristic over composition, faces, motion, text size, contrast, and object salience.

AI stack:

- Saliency model
- Face/object detection
- OCR bounding boxes
- Contrast and text-size heuristics
- Optical-flow motion emphasis

MVP:

- Generate per-frame attention overlays.
- Flag "message competition" when CTA/price overlaps with high-motion or low-contrast regions.
- Add a heatmap viewer in Evidence or DNA.

Demo punch:

- "The viewer's likely attention is pulled to the vehicle while the offer sits in low-contrast small text."

## 5. Audio-Visual Persuasion Mapper

Analyze voiceover, music, silence, sound effects, pacing, and visual beats together.

AI stack:

- Speaker/voice activity detection
- Audio event classification
- Music mood and tempo estimation
- Transcript alignment
- VLM beat labels

MVP:

- Extract audio segments with labels: voiceover, music, silence, impact sound.
- Align these to visual shots and OCR events.
- UI: audio waveform plus ad beat timeline.

Demo punch:

- "The offer appears during a noisy music swell; the CTA lands after voiceover stops."

## 6. Claim Grounding Graph

Build a graph of every extracted claim and connect it to the exact evidence that supports, qualifies, or conflicts with it.

AI stack:

- Claim extraction from transcript/OCR
- Entity linking
- Evidence retrieval
- Natural language inference style contradiction checks
- VLM verification on supporting frames

MVP:

- Extract claim nodes: price, offer, superlative, guarantee, comparison, urgency, credential, testimonial.
- Link nodes to OCR/transcript/frame evidence.
- Add graph viewer and agent tool: `explain_claim(ad_id, claim_id)`.

Demo punch:

- "Show me the evidence for '0% APR' and what qualifies it."

## 7. Counterfactual Creative Lab

Generate evidence-grounded alternate versions of the ad concept: offer-first, brand-first, proof-first, faster CTA, simpler end card, quieter disclaimer layout.

AI stack:

- LLM script rewriting
- VLM-informed beat analysis
- Entity-preserving generation
- Diff engine
- Optional image/video generation for still mockups

MVP:

- Input: `ad_id` plus a rewrite goal.
- Output: alternate script, beat list, end-card copy, changed entities, and source citations.
- Store generated alternatives under `data/out/{ad_id}/counterfactuals/`.

Demo punch:

- "Make this ad proof-first without inventing any new offer."

## 8. Campaign Drift Radar

Track how campaign variants evolve over time across product, offer, CTA, claim, visual motif, pacing, and DNA.

AI stack:

- Embedding trajectory analysis
- Entity diffing
- Temporal clustering
- VLM summaries of changes
- Anomaly/change-point detection

MVP:

- Compare ads inside one campaign by `ingested_at`.
- Generate drift events: offer changed, CTA changed, disclaimer changed, visual motif changed.
- Add campaign-level timeline and agent answers.

Demo punch:

- "This campaign shifted from financing to inventory urgency after May 10."

## 9. Synthetic Audience Tournament

Go beyond one synthetic panel: run multiple persona teams against multiple creative variants and produce an evidence-grounded bracket of objections, strengths, and edits.

AI stack:

- Persona simulation with strict caveats
- Debate-style critique
- LLM judge constrained by evidence
- Variant comparison
- Citation filtering

MVP:

- Use existing creative panel and debate outputs as primitives.
- Add a tournament endpoint that compares 2 to 6 selected ads or generated variants.
- Output: objection matrix, confusion matrix, strongest proof, and next-test suggestions.

Demo punch:

- "Which variant survives the skeptic, budget, luxury, and mobile-first debate?"

## 10. Generative Variant Factory

Generate a pack of production-ready creative variations from one grounded ad: shorter cutdown, different opening, alternate CTA, social caption, end-card text, and thumbnail concepts.

AI stack:

- LLM structured generation
- VLM frame selection
- Image generation or compositing for thumbnails
- Text-to-speech optional voiceover scratch
- Entity preservation and citation checks

MVP:

- Output JSON plus an HTML gallery.
- Every generated asset has a "source evidence" section and an "invented vs inherited" diff.
- Start with copy and static key visual mockups before video rendering.

Demo punch:

- "Turn this 30-second TV ad into 6 platform-ready concepts without losing the offer."

---

# 10 Analysis and Insight Features

These are practical analyst workflows that turn ARGUS data into strategy and diagnosis.

## 1. Hook and Payoff Timeline

Detect the first hook, first product reveal, first brand cue, first offer, first proof point, first CTA, and final payoff.

MVP:

- Use OCR/transcript/entities plus VLM labels over selected frames.
- Add a timeline panel with gaps and timing deltas.
- Agent question: "How long before the ad says what it is selling?"

Demo punch:

- "Product is clear at 1.5s, offer at 12.0s, CTA at 27.5s."

## 2. Offer and CTA Timing Benchmarks

Compare timing patterns across the local ad library.

MVP:

- Compute first offer timestamp, first CTA timestamp, end-card duration, and CTA repetition count.
- Group by brand, category, campaign, or creative DNA.
- UI: benchmark distribution with selected ad highlighted.

Demo punch:

- "This ad introduces the offer later than 83% of automotive ads in the local library."

## 3. Claim Specificity and Proof Ladder

Rank extracted claims by specificity: vague, concrete, quantified, qualified, evidenced.

MVP:

- Parse claims from OCR/transcript.
- Connect to claim grounding graph when available.
- Show a ladder: "fast service" < "same-day service" < "$49 service call today."

Demo punch:

- "The ad has strong emotional claims but only one concrete proof point."

## 4. Competitive White-Space Map

Visualize ads in a 2D/3D creative territory map using text/visual embeddings and DNA features.

MVP:

- Generate UMAP coordinates from ad-level vectors.
- Overlay brand, category, offer type, hook type, campaign, and observation tags.
- Add generated cluster labels with local LLM fallback.

Demo punch:

- "These three dealerships all occupy the same discount-heavy territory; nobody is using proof-led service creative."

## 5. Promise Match: Ad vs Landing Page

Compare the ad promise to optional landing-page metadata: product, offer, price, CTA, phone, URL, brand, and terms.

MVP:

- Use existing marketing entities plus landing-page metadata.
- Output matched, missing, changed, and ambiguous fields.
- Do not call it compliance. Call it handoff consistency.

Demo punch:

- "The ad says 0% APR; the landing page headline says lease offer; terms are not obviously aligned."

## 6. Creative Repetition and Fatigue Detector

Find repeated visual motifs, copy templates, offers, CTAs, and end-card layouts across campaigns.

MVP:

- Combine pHash, visual embeddings, OCR signatures, and entity diffs.
- Mark repeated modules: same opening shot, same price card, same CTA, same disclaimer block.
- Add campaign-level "template reuse" score.

Demo punch:

- "These 12 ads reuse the same end card with only the vehicle model swapped."

## 7. Brand Cue Density Score

Measure how frequently and how early brand cues appear: logo, brand name, tagline, URL/domain, spoken brand mention, and product design cues.

MVP:

- Use OCR, transcript, logo/object detection, and VLM verification.
- Output timing, repetition, and modality counts.
- Add a brand presence timeline.

Demo punch:

- "Brand is spoken at 0.8s but not visible until 24.0s."

## 8. Positioning Map

Classify each ad's strategic posture: budget/value, premium/status, trust/proof, urgency/scarcity, convenience, local/community, innovation, lifestyle, safety, transformation.

MVP:

- Local LLM classifier grounded in DNA, claims, entities, and transcript.
- Multi-label output with evidence citations.
- Map campaigns by posture mix.

Demo punch:

- "The brand's local ads are value-heavy, while competitors are shifting toward trust and convenience."

## 9. Message Collision Detector

Find places where the ad tries to communicate too many things at once: dense OCR, multiple CTAs, fast voiceover, overlapping offer and disclaimer, or competing visual focus.

MVP:

- Score each second by OCR density, transcript word rate, motion, and number of entity types.
- Output collision hotspots.
- Show "simplify this moment" suggestions.

Demo punch:

- "At 22s the ad shows price, CTA, phone, URL, and disclaimer while voiceover introduces a new offer."

## 10. Campaign Question Answering Packs

Generate pre-built, evidence-backed answers for common agency questions.

MVP:

- For each campaign, cache answers to:
  - What is the core message?
  - What changed over time?
  - Which ad is the clearest?
  - What are the top objections?
  - What should be tested next?
- Power the answers from structured tools, not raw SQL.

Demo punch:

- A campaign page that feels like a strategist already reviewed the whole library.

---

# 10 AI-Adjacent Product and Workflow Features

These features make the demo feel complete and operational. They use AI outputs, model evaluation, packaging, or human-in-the-loop workflows without being pure model research.

## 1. Auto Strategy Deck Generator

Generate a client-ready deck from a campaign or selected ads.

MVP:

- HTML first, PPTX later.
- Slides: overview, key frames, DNA comparison, moment timeline, offers, CTAs, drift, white-space map, panel/debate summary, next tests.
- Include citations and artifact paths.

Demo punch:

- "Select campaign -> generate deck -> show a polished agency deliverable."

## 2. Evidence Clip Reel Export

Create a short reel of the most important moments across one ad or campaign.

MVP:

- Use ffmpeg to cut clips around selected timestamps.
- Let AI choose moments: hook, offer, proof, CTA, contradiction, best visual.
- Export MP4 plus JSON manifest.

Demo punch:

- "Here are the 12 seconds that explain the whole campaign."

## 3. Creative Brief Generator

Turn analysis into a concise creative brief for the next iteration.

MVP:

- Inputs: selected ads/campaign, current findings, desired direction.
- Output: objective, audience caveat, core message, proof points, must-keep entities, avoid-list, CTA, timing plan, visual references.
- Every recommendation cites source ads.

Demo punch:

- "ARGUS becomes the strategist that writes the next brief from the evidence."

## 4. Prompt and Model Arena

A local evaluation page for OCR, VLM, entity extraction, DNA, debate, and generated variants.

MVP:

- Compare two prompts or two models on the same evidence bundle.
- Show JSON validity, citation coverage, missing entities, hallucinated entities, latency, token count, and fallback rate.
- Save eval runs locally.

Demo punch:

- "We can prove which local model is better on our own ad corpus."

## 5. Active Learning Correction Studio

Let analysts correct brand, product, offer, CTA, OCR, and category fields, then use those corrections to improve aliases, rules, prompts, and small model eval sets.

MVP:

- Correction UI with "use this as training/eval example" toggle.
- Export correction set as JSONL.
- Auto-suggest taxonomy/rule updates from repeated corrections.

Demo punch:

- The system gets visibly smarter from analyst corrections without needing a cloud labeling platform.

## 6. Demo Dataset Builder

Create a curated local demo pack with anonymized or synthetic ads, precomputed artifacts, and scripted "wow paths."

MVP:

- CLI: `argus demo build-pack`.
- Include DB snapshot, frames, OCR, transcripts, DNA, debates, search examples, and deck outputs.
- Frontend shows a Demo Mode badge and guided shortcuts.

Demo punch:

- Reliable demos without waiting for ingestion or depending on fragile model availability.

## 7. AI Runbook and Autopilot Queue

Let users queue analysis jobs like "run DNA for all finished automotive ads" or "refresh drift reports for campaigns changed this week."

MVP:

- Recipe definitions stored locally.
- Background job runner with SSE progress.
- Each recipe writes report artifacts and database metadata.

Demo punch:

- ARGUS looks like a system of AI workers, not a one-off script.

## 8. Insight Inbox

An AI-generated inbox of notable findings: new duplicate cluster, campaign drift, unusually late CTA, price mismatch, repeated template, low OCR confidence, strong white-space cluster.

MVP:

- Generate insight cards from deterministic triggers and optional LLM summaries.
- Cards link to evidence, ads, campaigns, and recommended next action.
- No gating language.

Demo punch:

- "ARGUS opens with the 10 things worth looking at today."

## 9. Shareable HTML Report Portal

Create static, local HTML reports for one ad, campaign, or search result set.

MVP:

- Export report folder with HTML, CSS, thumbnails, clips, JSON artifacts.
- Include evidence links, generated summaries, and caveats.
- Works without the backend running.

Demo punch:

- A polished artifact a creative director can open immediately.

## 10. Analyst Skill Macros

Let users save agent prompts and analysis workflows as named macros: "competitive sweep," "CTA audit," "campaign drift scan," "local dealership pack."

MVP:

- Store macros in SQLite.
- Macro can run tool calls, search queries, report generators, and exports.
- Frontend macro launcher with progress and result cards.

Demo punch:

- "One click runs a full agency analyst workflow across the ad database."

---

# Suggested Build Order by Demo Value

## Phase A: Fastest wow

1. Hook and Payoff Timeline
2. Multimodal Moment Search 2.0
3. Creative DNA Genome
4. Evidence Clip Reel Export
5. Auto Strategy Deck Generator

## Phase B: Strategic intelligence

6. Competitive White-Space Map
7. Campaign Drift Radar
8. Claim Grounding Graph
9. Creative Repetition and Fatigue Detector
10. Brand Cue Density Score

## Phase C: Advanced AI lab

11. Object Track and Brand Presence Graph
12. Counterfactual Creative Lab
13. Generative Variant Factory
14. Synthetic Audience Tournament
15. Prompt and Model Arena

## Phase D: Product polish

16. Insight Inbox
17. Active Learning Correction Studio
18. Creative Brief Generator
19. Shareable HTML Report Portal
20. Analyst Skill Macros

## Features intentionally excluded

- Standalone director-shot-list reconstruction.
- Generic creative-attribute filters unless they are part of a stronger moment search or DNA workflow.
- Disclosure-label systems not grounded in extracted evidence.
- Any review/gating workflow.
- Any claim that synthetic personas predict real market performance.
