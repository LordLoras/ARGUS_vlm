# Demo feature suggestions

These require **zero pipeline changes** — all use existing API/data. Sorted by demo impact.

---

## Frontend-only (quickest to build)

### 1. Share of Voice donut chart
Replace the flat category list on the library page with a colored donut/ring chart showing ad count by category. Makes the portfolio composition instantly visual.

**Files:** `Library.tsx`, `index.css`  
**Data:** Already available in `counts.byCategory`  
**Effort:** ~1 hour (chart component + legend)

### 2. Ad Timeline heatmap
Calendar grid showing ingest activity. Hover over a day to see how many ads were uploaded. Useful for spotting campaign seasonality ("most ads uploaded in March").

**Files:** `Library.tsx`, `index.css`  
**Data:** `ad.ingested_at` already in list response  
**Effort:** ~2 hours

### 3. Disclaimer Complexity Leaderboard
Rank ads by `disclaimer_density` (already extracted by VLM as "low/medium/high"). Shows which ads have the most fine print. Fun demo: "Show me the ad with the most disclaimers."

**Files:** `Library.tsx`, `Shared components`  
**Data:** `marketing_entities.creative_attributes.disclaimer_density` in detail API  
**Effort:** ~1 hour

### 4. Brand Adjacency Network
A graph/diagram connecting brands to their advertisers. Shows "Jeep" → "Iowa Jeep", "Dick Poe Chrysler Jeep", etc. Useful for dealer relationship analysis.

**Files:** `Library.tsx` or new page, `index.css`  
**Data:** `ad.brand_name` + `ad.advertiser_name` from list API  
**Effort:** ~3 hours (needs a graph layout library like d3-force or vis-network)

### 5. Ad comparison heatmap
Side-by-side comparison grid: pick 3-4 ads, see their attributes (brand, category, subcategory, price range, offer count, disclaimer density) as a colored heatmap. Makes cross-ad analysis instant.

**Files:** New component, `Library.tsx`  
**Data:** Already available from detail API  
**Effort:** ~3 hours

---

## Agent tool (one .py file each, no pipeline changes)

### 6. `competitive_brief` agent tool
Single tool call returns a structured cross-brand report:
```
Brand     Ads  Avg price   Top offers                Common CTAs
Jeep      12   $42,000     0% APR, $1k rebate        "Build yours"
Ford      8    $48,500     $750 bonus cash, 1.9% APR "Find your F-150"
```
Chains `count_ads`, `list_ads`, `aggregate` internally.

**Files:** `ad_classifier/agent/tools/competitive_brief.py`  
**Data:** Existing tools + repository methods  
**Effort:** ~2 hours

### 7. `ad_trend` agent tool
"Show me ad volume by month for the last 6 months." Returns a time series of ingest counts grouped by month, optionally filtered by category/brand.

**Files:** `ad_classifier/agent/tools/ad_trend.py`  
**Data:** `ads.ingested_at` + `ads.primary_category` from repository  
**Effort:** ~1 hour

### 8. `top_offers` agent tool
"What offers appear most frequently in automotive ads?" Returns the most common offer texts/patterns across ads, optionally filtered by category or brand.

**Files:** `ad_classifier/agent/tools/top_offers.py`  
**Data:** `marketing_entities.offers` JSON via repository  
**Effort:** ~2 hours

---

## Would need small backend changes

### 9. Real-time pipeline dashboard
Show worker status, queue depth, ads processed per minute, failure rate. A `/api/worker/stats` endpoint returning job queue metrics + a dashboard page.

**Files:** `api/routes/worker.py`, new frontend page  
**Data:** `jobs` table  
**Effort:** ~4 hours

### 10. Bulk CSV export
"Export all ads matching filter X as CSV." A `GET /api/ads/export?category=automotive` that returns `text/csv` with flat ad fields + marketing entity summary.

**Files:** `api/routes/ads.py`, frontend button  
**Data:** Existing repository methods  
**Effort:** ~2 hours

### 11. Keyword timestamp browser
Search for a word across all OCR/transcript, get back a timeline of where it appears in each ad. "Find me all ads that mention 'warranty'" with clickable timestamps.

**Files:** `api/routes/ads.py` (search endpoint), frontend page  
**Data:** `ocr_items.text` + `transcript_segments.text` via FTS  
**Effort:** ~3 hours

---

## Highest demo impact picks

| # | Feature | Effort | Demo wow factor |
|---|---------|--------|----------------|
| 1 | Share of Voice donut | 1h | ★★★★★ (instant visual data) |
| 6 | `competitive_brief` tool | 2h | ★★★★★ (feels like real analysis) |
| 4 | Brand Adjacency Network | 3h | ★★★★☆ (impressive graph viz) |
| 10 | Bulk CSV export | 2h | ★★★☆☆ ("we can take this to Excel") |
| 2 | Timeline heatmap | 2h | ★★★☆☆ (shows activity patterns) |
