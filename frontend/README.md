# ARGUS Frontend

Vite + React + TypeScript management UI for the local FastAPI backend that powers ARGUS — the Ad Retrieval, Graphing & Understanding System.

```powershell
npm install
npm run codegen
npm run dev
```

The app uses same-origin API requests by default. During local development,
Vite proxies `/api` and `/data` to `http://127.0.0.1:8000`, so a temporary
frontend tunnel is enough for remote testing.

For a temporary public demo domain, enable Basic Auth with an ignored local env
file before starting Vite:

```powershell
Set-Content .env.local @"
ARGUS_BASIC_AUTH_ENABLED=true
ARGUS_BASIC_AUTH_USERS=h-tech:change-this-password,analyst:another-password
ARGUS_BASIC_AUTH_REALM=ARGUS Demo
"@
npm run dev
```

Add users by adding comma-separated `username:password` pairs to
`ARGUS_BASIC_AUTH_USERS`, then restart Vite. Keep `ARGUS_BASIC_AUTH_ENABLED=false`
or unset for normal local-only development.

Override the proxy target only when your FastAPI server is on a different host:

```powershell
$env:VITE_API_PROXY_TARGET = "http://127.0.0.1:8001"
```

If you intentionally want the browser to call a separate API origin directly,
set:

```powershell
$env:VITE_API_BASE_URL = "https://api.example.test"
```

If you are testing over your LAN, bind Vite to all interfaces:

```powershell
$env:VITE_DEV_HOST = "0.0.0.0"
npm run dev
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
