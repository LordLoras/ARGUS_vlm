# Digital Video Ad Venues — Deep Research (collect-all-now, map-later)

> **Scope (locked with the user, 2026-06-24):** TV/broadcast ads are tracked elsewhere — this
> doc is **digital only**. Goal for now: **collect/scrape as many US digital video ad
> creatives as possible** with provenance + stable IDs; cross-venue and TV↔digital **mapping
> is deferred**. US market focus. This complements the brand-anchored awareness crawler
> (`ad_classifier/intelligence_crawler/`); each venue below becomes a `SourceAdapter`.
>
> Researched against current (June 2026) sources — see §9. Platform ToS/API access shifts
> often; re-verify any specific venue before building its adapter.

---

## 1. The one hard truth that shapes everything

**Almost every platform's *official ad-library API* is gated to political/issue ads and/or
the EU — not US commercial video.** Concretely:

- **Meta Ad Library API** → political & social-issue ads, **EU-only**. No commercial, no US
  via API. US commercial video *is* visible in the **web UI**, but there's no official bulk
  download/API for it.
- **TikTok Commercial Content Library/API** → **EEA/UK/Switzerland only**, gated to approved
  researchers, ~1,000 req/day. **No US data, no commercial-user access.**
- **Google Ads Transparency Center** → covers **US** verified advertisers incl. YouTube video
  ads, but has **no official public API** at all.

So for *US digital video* you cannot lean on first-party platform APIs the way you can for
YouTube uploads. The realistic collection strategy is a **mix of**: (a) the one genuinely
open official API (YouTube), (b) **licensed third-party APIs / managed scrapers** that assume
the ToS/anti-bot burden, and (c) optionally **paid ad-intelligence vendors** that already
collect normalized cross-platform video creatives. DIY-scraping Meta/Google/TikTok directly
is brittle and against ToS (see §7).

---

## 2. Venue catalog

Each entry: **coverage** (US digital video), **access**, **what you get / video**, **dedup
key**, **cost**, **ToS/risk**, **reliability**.

### A. First-party / owned video (the clean, free tier)

**A1. YouTube — official brand channels + YouTube ads**
- Coverage: where brands post the digital cut of nearly every national spot; also the surface
  for YouTube/Display *paid* video ads.
- Access: **YouTube Data API v3** (`channels.list` → uploads playlist → `playlistItems.list`,
  `videos.list`) and the **free channel Atom feed** `youtube.com/feeds/videos.xml?channel_id=`
  (no key, no quota — ideal for detection). Official, ToS-clean.
- You get: video id, title, description, publish date, duration, thumbnails, tags, stats, URL.
- Dedup key: **YouTube video id** (globally stable). Best dedup key of any venue.
- Cost: free (Data API quota ~10k units/day; feed is unmetered).
- Risk: low. The backbone venue.
- Reliability: ★★★★★ for owned video; partial for *paid* video (only what's on channels).

**A2. Vimeo — agency/brand case-study & spot reels**
- Coverage: agencies/production houses post finished spots and case studies here.
- Access: **Vimeo API** (official) by user/showcase; or page scrape.
- You get: video id, title, description, date, thumbnail, embed/URL, sometimes credits.
- Dedup key: Vimeo video id.
- Cost: free tier / API.
- Reliability: ★★★ — good for creative/campaign context, partial coverage.

**A3. Brand-owned sites & landing pages (embedded video)**
- Coverage: campaign hubs embed the hero video (often the same YouTube/Vimeo id).
- Access: sitemap/RSS + OpenGraph/JSON-LD `VideoObject` extraction (our RSS adapter path).
- Dedup key: canonical URL hash + embedded video id (often resolves to A1/A2).
- Reliability: ★★★ — mostly corroboration; embeds usually dedupe into YouTube/Vimeo.

### B. Platform ad-transparency libraries (the paid-social video surfaces)

**B1. Google Ads Transparency Center (ATC)** — *highest-value US paid-video surface*
- Coverage: **US** verified advertisers across Google **Search/Display/YouTube/Maps/Shopping**,
  incl. **video** creatives, with date ranges, formats, regions.
- Access: **no official API.** Reach it via **third-party APIs / managed scrapers** —
  SerpApi (`engine=google_ads_transparency_center`), SearchApi, Apify actors (~400 ads/min,
  text+image+**video**). Some open-source reverse-engineered scrapers exist.
- You get: advertiser, creative (incl. video), format, first/last shown dates, region.
- Dedup key: ATC creative/advertiser id (per provider) + landing URL.
- Cost: third-party API usage fees (per-result/credits).
- Risk: medium — official has no API; third-party tools carry the scrape risk for you.
- Reliability: ★★★★ — the single best "what video ads is this US advertiser running" source.

**B2. Meta Ad Library (Facebook + Instagram)** — *huge US social-video volume*
- Coverage: **all currently-running** US commercial ads incl. **video** are viewable in the
  **web UI**; this is the largest pool of US paid social video creative.
- Access: **API is EU/political-only** → for US commercial video you need **web scrape** or a
  **third-party API** (Apify "Facebook Ads Library" actor, AdLibrary.com, ScrapeCreators).
  No official first-seen/spend for commercial US.
- You get: creative (video via `ad_snapshot_url`/scrape), ad copy, CTA, page, active dates.
  Media files often need a second fetch.
- Dedup key: Meta ad archive id (`ad_archive_id`).
- Cost: third-party API fees; DIY scrape is free but brittle/ToS-violating.
- Risk: high for DIY (anti-bot, ToS); medium via licensed third-party.
- Reliability: ★★★★ for breadth via a third-party API; ★★ for fragile DIY scraping.

**B3. TikTok**
- Coverage: official **Commercial Content Library** is **EEA/UK/CH only** — *not US*. US TikTok
  video ads are only reachable via **ad-spy aggregators** (§D) or TikTok **Creative Center**
  "Top Ads" (limited, promotional sampling).
- Access: aggregator APIs (BigSpy, Minea, PiPiAds) or Creative Center scrape.
- Dedup key: TikTok video/ad id (per aggregator).
- Reliability: ★★★ only via aggregators; no clean official US path.

**B4. LinkedIn Ad Library** — weakest official tool: active creatives only, **no history, no
spend, no API**. Useful for B2B video presence; access via UI or aggregator. Reliability ★★.

**B5. X (Twitter)** — per-advertiser **CSV export** by handle/country/time range. Narrow but
official-ish. Reliability ★★.

**B6. Snapchat / Pinterest / Reddit** — varying transparency, largely **EU/DSA-driven**; thin
or no US commercial API. Reach via aggregators if needed. Reliability ★–★★ for US.

### C. Paid digital ad-intelligence vendors (buy normalized coverage)

These already crawl the digital ecosystem and sell **normalized cross-platform video creatives
+ spend/impression estimates**. Fastest way to "collect everything" without building N
scrapers — but enterprise-priced.

- **Pathmatics (Sensor Tower)** — digital display/**video**/native/social/mobile; creatives,
  landing pages, ad paths, impressions, spend. Strong US coverage. ★★★★
- **AdClarity (BIScience)** — ~180M creatives, 52 markets, 35k platforms, programmatic events;
  **AdClarity API / data feeds / exports** (machine-ingestible). Strong for video+programmatic. ★★★★
- **MediaRadar (+ Vivvix)** — creatives/placements across 30+ channels, daily; Vivvix adds
  TV/OOH/print and an **API** (heavier integration). ★★★★ (and overlaps your TV system).
- **Adbeat** — display/native, faster refresh on active campaigns. ★★★

Dedup keys vary by vendor (their creative id); all provide landing URL + first/last seen.

### D. Ad-spy aggregators & unified ad-library APIs (cheap breadth, video-heavy)

Mid-tier tools that index **video ad creatives across platforms** with one schema — the
pragmatic "scrape all digital now" shortcut.

- **AdLibrary.com API** — one programmatic interface + consistent schema across **Meta, TikTok,
  YouTube, Snapchat, Pinterest, LinkedIn, Google**. Strong fit for a unified adapter. ★★★★
- **ScrapeCreators** — API across **Facebook, Google, LinkedIn, Reddit** ad libraries. ★★★
- **BigSpy** — 1B+ creatives across **FB/IG/TikTok/YouTube**; broad discovery. ★★★
- **Minea / PiPiAds** — **TikTok**-strongest, e-commerce filters, engagement metrics. ★★★
- **Foreplay** — Meta Ad Library *workflow* (save/organize), not bulk collection. ★★

### E. Managed scraping infrastructure (run someone else's maintained scraper)

When you must scrape a venue with no API, rent a maintained actor instead of DIY:
- **Apify** actors (Meta Ad Library, Google ATC, etc.) — ~400 ads/min, video supported.
- **SerpApi / SearchApi** — Google ATC + others as structured JSON.
These shift anti-bot maintenance + (some) ToS exposure onto the vendor.

---

## 3. Comparison matrix (US digital video)

| Venue | US video coverage | Access | Official API? | Stable dedup id | Cost | Risk |
|---|---|---|---|---|---|---|
| YouTube (owned) | Owned spots: high | Data API + free feed | ✅ | video id | Free | Low |
| Vimeo | Partial | Vimeo API | ✅ | video id | Free | Low |
| Google ATC | Paid video: high | 3rd-party API/scrape | ❌ | creative id+URL | $ | Med |
| Meta Ad Library | Paid social video: high | scrape / 3rd-party API | ❌ (US commercial) | ad_archive_id | $/free | High DIY |
| TikTok | US: none official | aggregators | ❌ (US) | ad/video id | $ | Med |
| LinkedIn | Active only | UI / aggregator | ❌ | creative id | $/free | Med |
| X | Per-advertiser CSV | UI export | ~partial | ad id | Free | Low |
| Pathmatics/AdClarity/MediaRadar | Broad, normalized | vendor API/feed | ✅ (paid) | vendor id | $$$ | Low |
| AdLibrary.com / ScrapeCreators | Multi-platform | unified API | ✅ (3rd-party) | per-platform id | $$ | Low |

---

## 4. Recommended "collect all digital now" strategy

Given §1, sequence by value-per-effort and ToS-cleanliness:

1. **YouTube first (free, clean, best ids).** Owned-channel video via Data API + free feeds.
   This is the only large, ToS-clean, free US video source. Build this adapter first
   (already the Phase-3 stub in the module).
2. **Add one unified third-party API for paid social/display video breadth.** Rather than
   building separate fragile Meta/TikTok/Google scrapers, integrate **one** aggregator API
   (e.g. AdLibrary.com or ScrapeCreators) or a managed scraper (Apify/SerpApi for Google ATC +
   Meta). One adapter → many platforms, with the ToS/anti-bot burden on the vendor.
3. **Google ATC via third-party API** specifically for "what paid video is this US advertiser
   running" (highest-signal US paid-video surface with no official API).
4. **Optional paid vendor (Pathmatics / AdClarity / MediaRadar) if budget exists** — buys
   normalized, deduped, spend-attributed cross-platform video coverage in one feed, and
   MediaRadar/Vivvix overlaps your existing TV system for later mapping.
5. **TikTok via aggregator** (BigSpy/Minea/PiPiAds) only if US TikTok video matters.

**Maps cleanly onto the existing module:** each of the above is a `SourceAdapter`
(`source_type` registry). Owned-video adapters use official APIs; paid-social adapters wrap a
third-party/aggregator API; the runner, dedup, store, and signals are unchanged. "Collect
now, map later" = store every creative as an `intel_resource` with provenance + the venue's
stable id; defer cross-venue/TV mapping to the later matching phase.

---

## 5. What to capture per creative (so "map later" works)

Store enough that later dedup/mapping across venues — and against your TV-ad system — is
possible without re-scraping:
- **Stable venue id** (video id / ad_archive_id / vendor creative id) + **canonical URL**.
- **Media**: video URL + **thumbnail** (+ later a perceptual hash / sampled-frame hash — the
  cross-venue join key when ids differ).
- **Text**: title, ad copy, CTA, advertiser/page/brand, products mentioned.
- **Time**: first-seen / last-seen / publish or delivery dates (distinguish, per cold-start).
- **Provenance**: venue, access method, capture timestamp, raw payload.
- **Geo/platform/format** where available (to filter to US, and for later mapping).

The thumbnail/video perceptual hash is the most important "map-later" key: the *same* spot
appears on YouTube, Meta, and your TV system with different ids but near-identical frames.

---

## 6. Coverage reality check

- **Owned video (YouTube/Vimeo):** near-complete for what brands *choose* to publish; misses
  paid-only social cuts never posted to a channel.
- **Paid social/display (Meta/Google/TikTok):** only reachable via scrape / third-party /
  paid vendor — no free official US API. Coverage is as good as the provider you pick.
- **Nothing here covers broadcast TV** — that's your other system; this is the digital half.

---

## 7. Legality & ToS (decide the posture before building scrapers)

- **Prefer official APIs (YouTube, Vimeo) and licensed third-party APIs/vendors** over DIY
  scraping. DIY-scraping Meta/Google/TikTok violates their ToS, fights anti-bot systems, and
  breaks often.
- **Don't bypass logins, paywalls, rate limits, or bot checks.** Honor robots.txt for any
  direct HTTP.
- **Push scrape risk onto vendors** (Apify/SerpApi/SearchApi/AdLibrary.com) who operate the
  scrapers as their product, or onto paid intelligence vendors (Pathmatics/AdClarity) who
  license the data.
- **Store provenance + source-coverage limitations** on every record (e.g. "Meta US web
  scrape — active ads only, no spend").
- Keep adapters **disabled by default**; enable per venue after a ToS/cost review.

---

## 8. Open decisions

1. **Budget?** If a paid vendor (Pathmatics/AdClarity/MediaRadar) is in reach, it's the
   fastest path to "all digital video" and overlaps your TV data. If not, lean on YouTube +
   one aggregator/managed-scraper API.
2. **Which third-party API** for the multi-platform adapter — a unified ad-library API
   (AdLibrary.com / ScrapeCreators) vs managed scrapers (Apify/SerpApi) vs an enterprise
   vendor. (Trade-off: cost vs coverage vs schema quality.)
3. **TikTok in scope for US?** If yes, an aggregator is the only path.
4. **Media storage** — store thumbnails now (cheap, enables pHash mapping later) vs full video
   later (heavier, gated).

---

## 9. Sources

- [Meta Ad Library API guide (2026)](https://adlibrary.com/guides/facebook-ad-library-api) ·
  [Meta Ad Library free API 2026](https://adlibrary.com/posts/meta-ad-library-free-api-2026) ·
  [Meta Ad Library 2026 guide](https://superscale.ai/learn/how-to-use-the-meta-ad-library/)
- [TikTok Commercial Content API](https://developers.tiktok.com/products/commercial-content-api) ·
  [TikTok Ad Library API limitations (2026)](https://adlibrary.com/guides/tiktok-ad-library-api) ·
  [TikTok CCL support](https://support.tiktok.com/en/account-and-privacy/personalized-ads-and-data/commercial-content-library)
- [Google Ads Transparency Center API — SerpApi](https://serpapi.com/google-ads-transparency-center-api) ·
  [SearchApi ATC](https://www.searchapi.io/google-ads-transparency-center-api) ·
  [Apify Google ATC scraper](https://apify.com/scrapers-hub/google-ads-transparency-scraper/api)
- [Pathmatics (Sensor Tower)](https://sensortower.com/product/digital-advertising/pathmatics) ·
  [AdClarity](https://adclarity.com/product/) ·
  [MediaRadar digital intelligence](https://www.mediaradar.com/digital-intelligence) ·
  [MediaRadar alternatives 2026](https://improvado.io/blog/mediaradar-alternatives)
- [Ad library APIs guide: FB/Google/LinkedIn/Reddit (ScrapeCreators)](https://scrapecreators.com/blog/the-ultimate-guide-to-ad-library-apis-facebook-google-linkedin-and-reddit) ·
  [LinkedIn Ad Library 2026](https://adlibrary.com/posts/linkedin-ad-library-2026) ·
  [AdLibrary.com unified API](https://adlibrary.com/)
- [Best ad spy tools 2026 (free to API)](https://adlibrary.com/posts/best-ad-spy-tools-2026) ·
  [Best ad intelligence tools 2026](https://adlibrary.com/posts/best-ad-intelligence-tools-2026) ·
  [Best TikTok ad spy tools 2026](https://www.admapix.com/blog/best-practices/best-tiktok-ad-spy-tools)
