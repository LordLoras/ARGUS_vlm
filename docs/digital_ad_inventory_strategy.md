# Building a Digital Ad Inventory — Strategy & Vision

> **Audience:** leadership / decision-makers. This is the *why* and the *approach*, not an
> implementation spec. It argues for one thing: **build a complete, structured inventory of
> digital ad creatives — a digital mirror of the TV ad database we already operate.**
>
> **Scope guardrail (deliberate):** this document is **only about acquiring and structuring the
> digital ad inventory.** It does **not** propose how to match or map digital ads to our TV ads.
> That is a later phase; it becomes *easy and credible only once the inventory exists.* We are
> pitching the foundation, not the join.
>
> Companion engineering detail: [digital_video_ad_venues_research.md](digital_video_ad_venues_research.md)
> (the venue-by-venue catalog) and [intellegence_crawler.md](intellegence_crawler.md) (what we've
> already shipped). Researched against current (June 2026) sources — see §10.

---

## 1. The pitch in one paragraph

We already track **TV**: thousands of channels, every spot, who ran what and when. That database
is valuable precisely because it is *complete and structured*. **Digital is our blind spot** — the
same advertisers now spend the majority of their budgets on YouTube, streaming/CTV, social, and
the open programmatic web, and we see almost none of it. The move is **not** to "also do some
digital." It is to build a **Digital Ad Inventory**: a normalized, deduplicated, provenance-stamped
census of digital ad creatives, structured *like our TV database*, so it stands as a strategic asset
in its own right — and so that one day it can sit *next to* the TV data as a peer register. This doc
is about building that inventory the right way, from the cheap-and-easy sources all the way to the
exotic ones that reach into streaming and connected TV.

---

## 2. The core principle (this is the whole idea)

> **One canonical record per real-world ad creative, captured wherever it appears, with provenance
> and a stable identity — assembled into an inventory that mirrors the TV database's structure.**

Everything else is a consequence of this. Six sub-principles make it concrete:

1. **Inventory-first, not match-first.** Build the *census* of digital creatives before joining it
   to anything. A complete, well-structured inventory is independently valuable (creative trends,
   share-of-voice, "what is this brand running") and is the *precondition* for any future TV↔digital
   work. We earn the right to map by first owning the inventory.

2. **Symmetry with TV.** Give each digital record the **same spine** as a TV-ad record — advertiser,
   brand, product, creative, duration, first-seen / last-seen, market, a reference to the media. Two
   registers of the same kind. (How they get linked is out of scope here — but symmetry is what makes
   it *possible* later.)

3. **Capture-everything + provenance, always.** Every record is stamped with **where** it came from,
   **how** we got it (official API / licensed feed / managed scrape), **when** we captured it, the
   **raw payload**, and the **coverage caveats** of that source ("active ads only, no spend," etc.).
   Provenance is what makes the inventory trustworthy to an analyst and defensible to legal.

4. **Stable identity + content fingerprint as the spine.** Key every creative on the venue's stable
   id (YouTube video id, ad-archive id, vendor creative id) **plus** the media's own fingerprint
   (perceptual/audio hash). The fingerprint is what collapses *the same spot seen on three platforms*
   into **one** inventory item. (This is internal de-duplication — identity — not mapping to TV.)

5. **Media-anchored.** The atom of the inventory is the **creative itself** (the video/its frames and
   audio), not a row of metadata about it. Keep at least the thumbnail now; the media reference is the
   thing every future capability hangs off of.

6. **Append-only, observation-based, candidate-by-default.** Like the crawler we already ship: we
   *observe and record*, never destructively overwrite; new finds are candidates with confidence and
   evidence, never silent assertions. The inventory is an evidence ledger, not an opinion.

**Why this framing wins:** it turns an open-ended "go scrape the internet" project into a single,
legible asset with a clear definition of done-ness per source ("is this venue in the inventory, with
provenance, yes/no"). Leadership can fund it in tiers and measure coverage growth directly.

---

## 3. The acquisition spectrum — every way to fill the inventory

There is **no single firehose** for US digital ad creatives (unlike broadcast, almost every
platform's official ad-library API is gated to political ads or the EU — see the venue research §1).
So filling the inventory is a **portfolio**: combine sources by value-per-effort. Below is the full
spectrum, easy → exotic, each tagged with **what it adds**, **effort**, **cost**, **risk**. The later
tiers are the hard ones — and the ones that reach toward TV.

### Tier 0 — Owned / first-party media *(free, clean, build first — already shipped)*
Brands publish the digital cut of nearly every national campaign on their **own** channels.
- **YouTube** — Data API + the free, unmetered channel feed. Best ids of any venue (global video id).
- **Vimeo** — agency/production-house spot reels and case studies.
- **Brand sites & newsrooms** — embedded hero videos via sitemap/RSS + OpenGraph/JSON-LD `VideoObject`.
- *Adds:* the backbone of owned creative. *Effort:* low. *Cost:* free. *Risk:* low.
- **Status: built.** This is exactly the `intelligence_crawler` we already run.

### Tier 1 — Ad-transparency libraries *(the paid-social / display creatives)*
What advertisers are *running as paid ads* (not just posting).
- **Google Ads Transparency Center** — US verified advertisers across Search/Display/**YouTube**/etc.,
  including video, with date ranges. *No official API* → reach via managed scrapers.
- **Meta Ad Library** (Facebook+Instagram) — the largest pool of US paid social video; visible in the
  UI, but the **API is EU/political-only**, so US commercial needs scrape / third-party.
- **LinkedIn / X / TikTok** — thinner or non-US-official; reachable via aggregators.
- *Adds:* paid creatives brands never post to a channel. *Effort:* med. *Cost:* $. *Risk:* med (ToS).

### Tier 2 — Unified ad-spy / aggregator APIs *(cheap breadth, one schema)*
One API, many platforms — the pragmatic "fill a lot of the inventory fast" shortcut.
- **AdLibrary.com**, **ScrapeCreators**, **BigSpy**, **Minea / PiPiAds** (TikTok-strong).
- *Adds:* multi-platform creative volume with a single integration. *Effort:* low-med. *Cost:* $$.
  *Risk:* low (vendor carries the scrape).

### Tier 3 — Managed scraping infrastructure *(rent a maintained scraper)*
When a venue has no API, rent someone's maintained actor instead of building a brittle one.
- **Apify** actors (Meta Ad Library, Google ATC), **SerpApi / SearchApi** (ATC as structured JSON).
- *Adds:* venues with no API, without us owning the anti-bot fight. *Effort:* low. *Cost:* $$. *Risk:* med.

### Tier 4 — Enterprise digital ad-intelligence vendors *(buy normalized coverage)*
Firms that already crawl the digital ecosystem and **sell** normalized, deduped, spend-attributed
cross-platform creatives. The fastest way to "most of digital" in one feed — enterprise-priced.
- **Pathmatics (Sensor Tower)**, **AdClarity (BIScience)** (API/feeds, ~180M creatives), **MediaRadar
  / Vivvix**, **Adbeat**.
- *Adds:* broad, clean, deduped coverage + spend estimates on day one. *Effort:* low (integration).
  *Cost:* $$$. *Risk:* low. **Note:** MediaRadar/Vivvix also span TV/OOH/print — i.e. a vendor that
  already lives in *both* our worlds.

### Tier 5 — The TV-bridge tier *(the hard, high-value ones — where digital meets the screen)*
This is the tier leadership should care about most, because **the same 30-second spot that runs on
broadcast increasingly also runs on streaming/CTV** — so these sources are where the digital inventory
starts to overlap the world our TV system already watches. They are harder, costlier, and partner- or
device-dependent. (We are still only *building the inventory* here — not yet joining it to TV.)

- **5a. CTV / streaming ad-occurrence intelligence.** Vendors that track *every second of TV **and**
  streaming*. **iSpot** alone reports a catalog of **2.5M+ creatives**, data from **83M smart TVs**,
  and integrations with **400+ streaming platforms and DSPs**. Buying/partnering here adds the
  streaming-ad creatives directly. *Effort:* low (integration). *Cost:* $$$. *Risk:* low.

- **5b. ACR (Automatic Content Recognition) data licensing.** Smart-TV makers fingerprint *what is
  actually on screen* across millions of sets and **license** that data — **Samba TV** (Sony,
  Toshiba, Panasonic, ~24 brands), **Inscape** (Vizio), **Nielsen/Gracenote**. This is the literal
  surface where broadcast and streaming ads are observed in the same stream. *Adds:* ground-truth
  "this creative actually aired/streamed." *Effort:* med (legal + integration). *Cost:* $$$.
  **Risk: elevated — privacy/regulatory.** ACR is under active scrutiny (e.g. Samsung's Feb-2026
  settlement with the Texas AG over consent). **License from a compliant vendor; never DIY.**

- **5c. Real-device / sentinel panels.** Instrumented devices or virtual set-top boxes that *actually
  play* streaming/CTV apps and **capture the ad creatives served to them** (the approach behind tools
  like **Witbe**'s ad monitoring). This is the **only** way to obtain CTV creatives that never appear
  on any public channel or library. *Adds:* otherwise-invisible streaming/CTV creative. *Effort:*
  **high** (device farm or partner). *Cost:* $$–$$$. *Risk:* med.

- **5d. Programmatic / ad-tech capture.** Harvest creatives at the *ad-serving* layer — **VAST/VPAID**
  tags, the **IAB Tech Lab CTV programmatic** standards, **OM SDK** verification signals, and DSP/SSP
  creative feeds. *Adds:* creatives as they're trafficked, before/independent of where they render.
  *Effort:* high (ad-tech integration / partner). *Cost:* $$. *Risk:* med.

- **5e. AI ad-detection over captured streams.** The *capability* that turns raw 5b/5c stream capture
  into structured creative records — modern detectors spot **new** commercials and brand assets
  **without a reference fingerprint**, learning creative patterns (logos, phrases, motifs). This is
  exactly the kind of multimodal classification our pipeline already does for submitted ads, pointed
  at a live capture feed. *Adds:* automation that makes device/ACR capture scale. *Effort:* high (but
  reuses our core competency). *Cost:* compute. *Risk:* low.

### Tier 6 — Partnerships, data co-ops & first-party deals *(force-multipliers)*
- Agency / ad-verification-vendor data sharing, broadcaster & publisher data deals, and — if we have
  ad-serving clients — **our own first-party tags** as a clean, consented creative feed.
- *Adds:* consented, high-quality coverage we don't have to scrape. *Effort:* med (BD/legal). *Cost:*
  varies. *Risk:* low.

---

## 4. What a single inventory record looks like (the asset definition)

Capture enough, per creative, that the inventory is analyst-ready and *map-ready* later **without
re-collecting**. Deliberately the same spine as a TV-ad record:

| Field group | Contents |
|---|---|
| **Identity** | venue id (video/ad-archive/vendor id) · canonical URL · **content fingerprint** (perceptual + audio hash) |
| **Who** | advertiser · brand · product(s) · (parent company) |
| **Creative** | title · ad copy / CTA · **duration** · format (video/display/audio) · language |
| **Media** | thumbnail (now) · video/audio reference · sampled frames (later) |
| **Time** | first-seen (us) · last-seen · publish / delivery dates (kept distinct) |
| **Where** | platform · venue · placement/format · geo (US filter) |
| **Provenance** | source · access method · capture timestamp · raw payload · **coverage caveats** |
| **Confidence** | is-this-an-ad score · evidence · candidate/corroborated status |

The **fingerprint + duration + media** are the fields that make this inventory a peer of the TV
database rather than a pile of links. (Again: *how* the two registers get linked is the deferred
phase — we are only ensuring the digital side is shaped so that it can be.)

---

## 5. How we'd actually build it — crawl, walk, run

A tiered roadmap leadership can fund and measure by **coverage**, not by lines of code.

- **Crawl (now → built):** Tier 0 owned media (YouTube + Vimeo + brand newsrooms) **+** one Tier-2
  aggregator API for paid-social breadth. Cheap, ToS-clean, already largely shipped. *Milestone:
  inventory of owned + a slice of paid creative, with provenance.*

- **Walk:** add **Tier 1 Google ATC** (highest-signal US paid-video surface) via a managed scraper,
  **+** one **Tier-4 vendor feed** if budget allows (instant normalized breadth + spend). *Milestone:
  inventory covers owned + paid social/display across the major platforms.*

- **Run (the TV-bridge):** add **Tier 5** — a CTV/streaming-occurrence partner (5a) and/or **licensed
  ACR** (5b), fed into **our AI ad-detection** (5e), optionally backed by a **sentinel panel** (5c)
  for the long tail. *Milestone: inventory now includes streaming/CTV creatives — the same universe of
  screens our TV system watches.* This is the point at which the digital and TV registers are finally
  describing the same advertising reality, and the (separately-scoped) mapping work becomes credible.

Each tier slots into the **same architecture** we already run: every source is a self-contained
adapter behind one registry; the store, dedup, scoring, and signal model don't change when a venue is
added. We've proven this works — the existing crawler is exactly this pattern.

---

## 6. Why us, why now

- **We already own the hard half.** A complete **TV** ad register and a working **multimodal
  ad-understanding pipeline** (frames, transcript, OCR, classification, embeddings). Digital is the
  missing symmetric half — and Tier-5e (AI detection over captured streams) is *our existing core
  competency* pointed at a new feed.
- **The market is converging on the screen.** CTV ad spend hit ~$30B in 2025 and is tracking toward
  ~$40B in 2026; the same creatives now run across broadcast *and* streaming. A TV-only view is
  shrinking in relevance every quarter.
- **First-mover structure beats latecomer scramble.** Whoever holds the *structured, provenance-clean*
  digital inventory holds the asset everyone else will have to buy or rebuild.

---

## 7. The decision in front of us (what we're asking for)

The strategy scales with budget. Three fundable postures:

| Posture | Sources | Rough cost | Coverage |
|---|---|---|---|
| **Lean** | Tier 0 (built) + one Tier-2 aggregator | $ | Owned + a slice of paid social |
| **Standard** | + Tier 1 ATC (managed scrape) + one Tier-4 vendor feed | $$–$$$ | Most US paid social/display + spend |
| **Full / TV-bridge** | + Tier 5 (CTV-occurrence partner and/or licensed ACR + sentinel panel + our AI detection) | $$$$ | Streaming/CTV included — peer to the TV register |

**Ask:** approve the **Standard** posture now (it's mostly integration on top of what we've built),
and fund a scoped evaluation of **one** Tier-5 TV-bridge partner (iSpot-class occurrence data **or** a
licensed-ACR feed) to prove the streaming-creative inventory before committing to Full.

---

## 8. Risks & how we hold them

- **No US official APIs for most paid venues** → we **buy/partner** (Tiers 2–5) rather than DIY-scrape;
  the vendor carries the ToS/anti-bot burden. DIY scraping of Meta/Google/TikTok is brittle and against
  ToS — explicitly avoided.
- **ACR privacy/regulatory headwinds** (Tier 5b) → license only from compliant, consented vendors;
  treat ACR as *optional* and gated behind a legal review. Never operate it ourselves.
- **Coverage gaps are honest, not hidden** → every record carries its source's coverage caveat, so the
  inventory never over-claims.
- **Cost creep** → tiered roadmap; each tier is independently valuable and independently fundable.

---

## 9. The one-line version for the room

> *We own the most complete TV ad database in the business. Let's build its digital twin — a
> structured, provenance-clean inventory of every digital ad creative, from free owned-media all the
> way to streaming and connected TV. Own the inventory first; everything else (including connecting it
> to TV) is downstream of having it.*

---

## 10. Sources

- CTV/OTT scale & vendors: [Business of Apps — Top CTV platforms 2026](https://www.businessofapps.com/ads/ctv-advertising/) ·
  [AI Digital — CTV advertising trends 2026](https://www.aidigital.com/blog/ctv-advertising-trends)
- CTV/TV ad occurrence intelligence: [iSpot — competitive measurement](https://www.ispot.tv/products/measurement/competitive) ·
  [iSpot](https://www.ispot.tv/) · [Starti — TV/CTV ad analytics guide 2026](https://starti.ai/blog/tv-ad-analytics-ultimate-guide-to-ctv-insights-and-roi-2026/)
- ACR data licensing & ecosystem: [AdExchanger — marketer's guide to ACR](https://www.adexchanger.com/ad-exchange-news/the-marketers-guide-to-acr-tech-in-smart-tvs/) ·
  [AdExchanger — walled gardens around ACR](https://www.adexchanger.com/tv-2/the-rise-of-the-walled-gardens-around-acr-tech-in-smart-tvs/) ·
  [Digiday — WTF is ACR](https://digiday.com/future-of-tv/wtf-is-automatic-content-recognition/) ·
  [TV Tech — Nielsen/Vizio smart-TV data deal](https://www.tvtechnology.com/news/nielsen-inks-new-smart-tv-data-deal-with-vizio)
- ACR regulatory: [Captain Compliance — ACR privacy](https://captaincompliance.com/education/privacy-alert-how-automated-content-recognition-acr-is-watching-everything-you-watch/) ·
  [Smart TV ACR 2026 (Samsung/Texas)](https://cybershieldtips.com/article/smart-tv-acr-spying-disable-samsung-lg-sony-vizio-roku-2026)
- Real-device / sentinel capture & AI ad-detection: [Witbe — ad monitoring](https://www.witbe.net/use-cases/ad-monitoring/) ·
  [Digital Nirvana — automated ad detection for broadcasters](https://digital-nirvana.com/blog/real-time-compliance-monitoring-broadcast/)
- Programmatic / ad-tech capture: [Epom — video ad serving (VAST/VPAID/OMID) encyclopedia](https://epom.com/blog/ad-server/video-ad-serving-encyclopedia) ·
  [IAB Tech Lab — CTV programmatic guide](https://iabtechlab.com/standards-old/ctv-programmatic-guide/)
- Venue-level detail & vendor catalog: [digital_video_ad_venues_research.md](digital_video_ad_venues_research.md) (internal)
