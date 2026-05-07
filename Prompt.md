# Claude Code Prompt: AdScope App/API Implementation Handoff

Assume `AGENTS.md` already exists in the repository. Follow it.

This prompt is for implementing the user-facing app and API integration from a Claude Design handoff. It is not a backend pipeline rewrite prompt. The backend is the source of truth; the frontend must consume JSON over HTTP/SSE and stay decoupled from worker internals.

## Product Context

AdScope is a local-first multimodal ad analysis system. The backend ingests video ads, extracts OCR/transcript/frame evidence, classifies ads, extracts marketing entities, stores embeddings, tracks campaigns, and exposes a FastAPI API.

The frontend should be an analyst workspace for:

- uploading video ads and tracking processing jobs;
- browsing ads and campaign groups;
- inspecting classification, evidence, OCR/transcript/frame data, and marketing entities;
- searching by keyword, semantic text, visual similarity, or hybrid search;
- managing campaigns and ad assignments.

Do not build a marketing landing page. Build the actual operational app as the first screen.

## Implementation Priorities

1. Use the FastAPI OpenAPI schema as the API source of truth.
2. Keep frontend and backend decoupled. No backend assumptions beyond documented HTTP/SSE contracts.
3. Implement dense, work-focused UI suitable for repeated analyst use.
4. Preserve evidence provenance: timestamps, frame indexes, source type, confidence, bbox when present.
5. Treat categories and risk labels as descriptive analytics only. There is no gating/review workflow.
6. Do not add cloud services, Docker, auth, payments, or external telemetry.

## Backend API Surface

Base URL is local and configurable, default:

```text
http://127.0.0.1:8000
```

OpenAPI is available from FastAPI:

```text
GET /openapi.json
```

Claude Code should fetch or import this schema during implementation when possible and generate local TypeScript types/client helpers from it.

### Ads

```text
POST   /api/ads/upload
GET    /api/ads
GET    /api/ads/{ad_id}
PATCH  /api/ads/{ad_id}
DELETE /api/ads/{ad_id}
GET    /api/ads/{ad_id}/frames
GET    /api/ads/{ad_id}/evidence
GET    /api/ads/{ad_id}/similar
```

`POST /api/ads/upload`

- multipart file field: `file`
- allowed content: `.mp4`, `.mov`, `.webm`
- returns `{ ad_id, job_id, state, duplicate_of? }`
- if exact duplicate and dedup is enabled, `job_id` can be `null`.

`GET /api/ads`

Query params:

- `brand?: string`
- `category?: string`
- `status?: string`
- `q?: string`
- `limit?: number`
- `offset?: number`

Returns:

```json
{
  "items": [
    {
      "id": "ad_xxxxxxxx",
      "source_path": "string",
      "ingested_at": "ISO timestamp",
      "duration_ms": 0,
      "width": 0,
      "height": 0,
      "fps": 0,
      "status": "new|processing|completed|failed|duplicate|review",
      "brand_name": "string|null",
      "brand_confidence": 0.0,
      "advertiser_name": "string|null",
      "website_domain": "string|null",
      "phone_number": "string|null",
      "landing_page_domain": "string|null",
      "products_text": "string|null",
      "primary_category": "string|null",
      "decision": "allow|flag|review|null",
      "source_hash": "string|null",
      "phash_mean": "string|null"
    }
  ],
  "limit": 50,
  "offset": 0
}
```

`GET /api/ads/{ad_id}`

Returns:

```json
{
  "ad": {},
  "classification": {},
  "marketing_entities": {},
  "campaigns": []
}
```

### Jobs And SSE

```text
GET  /api/jobs/{job_id}
POST /api/jobs/{job_id}/cancel
GET  /api/jobs/{job_id}/events
```

`GET /api/jobs/{job_id}/events` is Server-Sent Events.

Event names:

- `job`: state/progress update
- `done`: terminal state
- `error`: job not found or stream error

Job event payload:

```json
{
  "type": "job",
  "job_id": "job_x",
  "state": "queued|running|completed|failed|cancelled",
  "progress": 0.0,
  "message": "string|null",
  "error": "string|null"
}
```

### Search

```text
GET /api/search
```

Query params:

- `mode=keyword|text|visual|hybrid`
- `q?: string`
- `ad_id?: string`
- `k?: number`

Rules:

- keyword requires `q`
- visual requires `ad_id`
- text requires `q` or `ad_id`
- hybrid requires `q` or `ad_id`

Return shape:

```json
{
  "mode": "hybrid",
  "items": []
}
```

Items differ by search mode. Render defensively and link every hit by `ad_id`.

### Campaigns

```text
GET    /api/campaigns
POST   /api/campaigns
POST   /api/campaigns/discover
POST   /api/campaigns/discover/accept
GET    /api/campaigns/{campaign_id}
PATCH  /api/campaigns/{campaign_id}
DELETE /api/campaigns/{campaign_id}
POST   /api/campaigns/{campaign_id}/ads
DELETE /api/campaigns/{campaign_id}/ads/{ad_id}
```

Campaign fields:

- `id`
- `name`
- `advertiser`
- `brand`
- `theme`
- `start_date`
- `end_date`
- `created_by: auto|user`
- `description`
- `created_at`

## Core Data Schemas

### Classification

Classification contains:

- `primary_category`
- `risk_labels`
- `confidence`
- `decision`
- `needs_human_review`
- `ocr_quality`
- `vlm_raw`
- `evidence`
- model/prompt/embedder/pipeline version metadata

`decision` is currently legacy-compatible and informational. Do not design a moderation queue around it.

Evidence item:

```json
{
  "time_ms": 0,
  "frame_index": 0,
  "source": "ocr|paddlevl|transcript|visual|rule|vlm",
  "text": "string",
  "bbox": [0, 0, 0, 0],
  "confidence": 0.0,
  "reason": "string"
}
```

### Marketing Entities

Marketing entities are the main app inspection schema. Render empty arrays/objects gracefully.

Top-level groups:

```text
brand
products
prices
offers
ctas
social_proof
disclaimers
creative_format
contact_points
advertiser
landing_page
offer_terms
creative_attributes
campaign_signals
```

Important nested fields:

- `contact_points.websites[]`: `url`, `domain`, `display_text`, `evidence`
- `contact_points.phone_numbers[]`: `raw`, `normalized`, `type`, `evidence`
- `contact_points.social_handles[]`: `platform`, `handle`, `url`, `evidence`
- `contact_points.app_store_links[]`: `platform`, `url`, `app_name`, `evidence`
- `contact_points.qr_codes[]`: `present`, `decoded_text`, `destination_hint`, `evidence`
- `advertiser`: `advertiser_name`, `brand_name`, `parent_company`, `service_area`, `locations`, `evidence`
- `landing_page`: `url`, `domain`, `path`, `utm_params`, `final_url`, `evidence`
- `offer_terms`: `promo_codes`, `expiry`, `financing`, `trial_terms`, `guarantees`, `scarcity_signals`, `urgency_signals`
- `creative_attributes`: `format`, `aspect_ratio` (`1:1|9:16|16:9|4:5|4:3`), `duration_ms`, `voiceover`, `music`, `testimonial`, `before_after`, `demo`, `ugc_style`, `end_card`, `disclaimer_density`
- `campaign_signals`: `slogan`, `recurring_offer`, `product_model`, `sku`, `creative_variant`, `campaign_theme`, `evidence`

Display all evidence-backed fields with timestamp/frame jump affordances when frame data is available.

## App UX Requirements

Build an operational dashboard, not a hero site.

Primary views:

1. Upload/Queue
   - drag/drop upload
   - job progress via SSE
   - recent uploads and failures

2. Ads List
   - dense table with status, brand, advertiser, category, website, phone, products, confidence, duration
   - search and filters
   - row click opens detail

3. Ad Detail
   - summary header with brand, advertiser, category, confidence, status
   - media/frame strip
   - tabs for Overview, Evidence, Marketing Entities, Frames/OCR, Similar Ads, Campaigns, Raw JSON
   - timestamped evidence list with source badges

4. Marketing Entities
   - grouped sections matching the schema above
   - contact points and offer terms should be prominent
   - do not hide empty sections if they explain data coverage; collapse them by default

5. Search
   - keyword/text/visual/hybrid mode selector
   - query input and optional selected ad as seed
   - results link to ad detail

6. Campaigns
   - campaign list and detail
   - manual assignment/unassignment
   - discovery action and accept flow

## Claude Design Handoff Contract

Claude Design should provide:

- design intent and target user;
- page inventory and responsive breakpoints;
- component inventory;
- typography, color, spacing, radius, shadow, and interaction tokens;
- key screens as images or structured descriptions;
- empty/loading/error states;
- icon guidance;
- any asset files or asset prompts.

Claude Code should implement the design handoff as follows:

1. Read the existing frontend stack and conventions before editing.
2. Map design tokens into Tailwind/theme variables rather than hardcoding one-off values everywhere.
3. Create reusable components for repeated UI patterns: tables, evidence rows, entity sections, status badges, confidence meters, frame thumbnails, campaign chips, search result rows.
4. Implement layout and visual system first with typed fixture data only when needed.
5. Replace fixtures with API client calls as soon as core components exist.
6. Use the OpenAPI schema or local API model types for all API responses.
7. Add loading, empty, error, and retry states for every remote view.
8. Wire upload progress using SSE, not polling, unless SSE fails.
9. Keep raw JSON views available for debugging but do not make them the primary UX.
10. Test the app against the local FastAPI server and sample data.

## Frontend Technical Guidance

Preferred frontend stack:

- Vite
- React
- TypeScript
- Tailwind
- shadcn/ui where already installed or requested
- lucide-react for icons

API client guidance:

- centralize `API_BASE_URL`;
- wrap `fetch` in a small typed helper;
- surface HTTP errors with useful messages;
- keep response parsing defensive;
- use `EventSource` for `/api/jobs/{job_id}/events`;
- avoid duplicating backend business logic in frontend.

State guidance:

- local component state is fine for small flows;
- use a query/cache library only if it is already installed or clearly useful;
- keep upload progress and job state resilient to refresh by refetching job/ad state.

Visual guidance:

- dense but readable analyst UI;
- 8px or smaller card radius unless existing system differs;
- no decorative gradient/orb backgrounds;
- no marketing-style hero;
- icons for compact actions;
- tables and panels should scan well with many ads;
- every button and badge must fit at mobile and desktop widths.

## Acceptance Criteria

An implementation is acceptable when:

- `npm run build` succeeds if a frontend exists;
- backend API calls work against `http://127.0.0.1:8000`;
- upload returns a queued job and the UI follows it via SSE;
- ad detail renders classification, marketing entities, evidence, frames, similar ads, and campaigns without crashing on missing fields;
- search modes handle required params and error states;
- campaign CRUD and assignment flows work;
- no mock data remains in production paths unless clearly labeled as fixture/dev mode;
- TypeScript types cover API responses used by the UI.

## Do Not Do

- Do not rewrite the Python pipeline from this prompt.
- Do not couple the backend to a specific frontend.
- Do not add cloud services or Docker.
- Do not install or upgrade PyTorch.
- Do not create a moderation/review queue from `decision` or `risk_labels`.
- Do not silently drop evidence metadata.
- Do not build a landing page instead of the analyst app.
