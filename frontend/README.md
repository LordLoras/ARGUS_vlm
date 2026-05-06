# AdScope Local Frontend

Vite + React + TypeScript management UI for the local FastAPI backend.

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
