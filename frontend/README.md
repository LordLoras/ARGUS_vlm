# ARGUS Frontend

Vite + React + TypeScript management UI for the local FastAPI backend that powers ARGUS — the Ad Retrieval, Graphing & Understanding System.

```powershell
npm install
npm run codegen
npm run dev
```

The app defaults to `http://localhost:8000` for the API. Override with:

```powershell
$env:VITE_API_BASE_URL = "http://localhost:8000"
```

All network access is routed through `src/lib/api-client.ts`. The generated OpenAPI client can be refreshed once the backend is running with `npm run codegen`.

## Pages

- `/library` — table, filter sidebar, ad detail drawer with Overview / Evidence / Related / Edit tabs
- `/upload` — dropzone, pipeline progress (SSE), result hero
- `/search` — keyword / text / hybrid / visual modes
- `/campaigns` — auto-discovered + user-curated campaign cards
- `/agent` — tool-calling chat backed by the Phase 9 agent endpoints (graceful empty state until those land)

## Design system

Tokens, typography, and component styles live in `src/index.css`. Tailwind is wired to those CSS variables in `tailwind.config.ts`, so utility classes (`text-fg-mute`, `bg-bg-1`, `font-mono`, `rounded-lg`) compose with the design tokens.
