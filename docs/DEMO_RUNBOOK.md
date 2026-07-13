# ARGUS Watcher — Demo Runbook

> Last updated 2026-07-13.

## Start / Access

- Start everything: `.\start.bat`
- Stop everything: `.\stop.bat`
- Local URL: `http://localhost:5173/experimental/watcher`
- Tunnel URL, if configured: `https://argus.rest/experimental/watcher`
- Demo login: `h-tech` / `argusdemo` from `frontend/.env.local`

If you only need the Watcher and not the worker:

```powershell
.\.venv\Scripts\python.exe -u -m ad_classifier api --host 127.0.0.1 --port 8000
npm --prefix frontend run dev -- --host 127.0.0.1 --port 5173
```

## Current Demo Dataset

The crawler DB was reset and repopulated on 2026-07-13 for a small, reliable demo.

| Brand | Source | Resources | Notes |
|---|---|---:|---|
| McDonald's | Google Ads Transparency Center | 9 | Small safe ATC set; includes video creatives with YouTube links/posters. |
| McDonald's | Meta Ad Library | 172 | Visible cards with screenshots, copy, library IDs, media URLs where exposed, and version counts. |

Watcher should show:

- `10` brands from the seed/watchlist.
- `2/17` enabled sources.
- `181` resources.
- McDonald's selected with both Google and Meta enabled.

Screenshots from before/after the reset live in:

```text
output/intel_demo_screenshots/
```

## What To Show

1. Open Watcher.
2. Select **McDonald's**.
3. Show the source cards: Google Ads Transparency + Meta Ad Library, both enabled.
4. Scroll to **Resources captured**.
5. Use adapter filter:
   - `All adapters`
   - `Google Ads Transparency`
   - `Meta Ad Library`
6. Use sort:
   - `Video first` to show richer cards.
   - `Most versions` to show Meta multi-version counts.
7. Open original provider links from cards:
   - `View on ATC`
   - `View in Ad Library`

## Live Run Guidance

Safe live run:

```powershell
python -m ad_classifier intel crawl --source mcdonalds_atc
```

Expected behavior:

- first fresh DB run: `new_resources=9`, `backfilled=9`, `baseline=true`;
- later re-run: existing rows refresh in place, no duplicate resources.

Avoid live during the demo:

```powershell
python -m ad_classifier intel crawl --source mcdonalds_meta_ads
```

Meta is browser-driven and can take minutes. Run it before the demo if you need to refresh.

Do not run broad ATC sources on stage (`apple_atc`, `ford_atc`, `toyota_atc`, etc.).
Repeated Google ATC requests can trigger HTTP 429 after heavy testing. If that happens,
wait and use the cached DB.

## Reset / Rebuild The Demo DB

Only delete the crawler DB, not the submitted-ad DB:

```powershell
Remove-Item .\intelligence_crawler.db, .\intelligence_crawler.db-shm, .\intelligence_crawler.db-wal -ErrorAction SilentlyContinue
python -m ad_classifier intel crawl --source mcdonalds_atc
python -m ad_classifier intel crawl --source mcdonalds_meta_ads
```

Then enable only the two McDonald's sources if needed:

```powershell
@'
import sqlite3
conn = sqlite3.connect("intelligence_crawler.db")
conn.execute("""
UPDATE intel_sources
SET enabled = 1, updated_at = datetime('now')
WHERE id IN ('mcdonalds_atc', 'mcdonalds_meta_ads')
""")
conn.commit()
'@ | .\.venv\Scripts\python.exe -
```

## Known Caveats

- The crawler stores raw metadata and normalized JSON; it does not OCR/classify these ads yet.
- Remote Meta media URLs can expire; local screenshots remain the durable visual fallback.
- Google ATC has no official US commercial API. The adapter uses the ATC internal RPC.
- Meta's official API does not return US commercial ads; the adapter reads the public UI.
- `delivery.regions` is normally empty in the US demo. The requested market is stored in
  `normalized.collection.requested_region_code`.
