# FlightStrip

Free pilot kneeboard generator that shows airports along your route with live METAR weather, frequencies, runway info, and contextual affiliate links. Powered by FAA NASR data refreshed every 28 days.

## Local Development

```bash
# 1. Clone
git clone https://github.com/jim0425/flightstrip.git
cd flightstrip

# 2. Install Python dependencies
pip install -r backend/requirements.txt

# 3. Download FAA NASR data (creates data/airports.db)
python scripts/download_nasr.py

# 4. Start the API server
uvicorn backend.main:app --reload --port 8000

# 5. Open frontend/index.html in your browser
```

## API Endpoints

| Method | Path | Description |
|--------|------|-------------|
| GET | `/health` | Health check with NASR version |
| GET | `/airport/{icao}` | Single airport detail with live METAR |
| POST | `/route` | Route airports with weather (JSON body: `{"from":"KBJC","to":"KSUN","corridor_nm":25,"mode":"vfr"}`) |
| GET | `/route/pdf?from_icao=KBJC&to_icao=KSUN` | PDF/HTML kneeboard export |

### Route modes
- **vfr** -- Shows CTAF, UNICOM, ATIS, AWOS, TWR, GND frequencies
- **ifr** -- Shows all frequencies including APCH, DEP
- **student** -- Same as VFR plus student tips (traffic pattern entry, etc.)

## Deploy

### Backend (Railway)
1. Push to GitHub
2. Connect repo to Railway
3. Railway auto-detects `railway.json` start command
4. Set `PORT` env var (Railway does this automatically)

### Frontend (Vercel)
1. Set root directory to `frontend/`
2. `vercel.json` handles SPA routing
3. Set `window.FLIGHTSTRIP_API_URL` in index.html to your Railway URL

## NASR Data Refresh

FAA NASR data updates on a 28-day cycle. The GitHub Actions workflow (`.github/workflows/refresh_nasr.yml`) runs on the 1st and 29th of each month to download fresh data and commit the updated `airports.db`.

To manually refresh:
```bash
python scripts/download_nasr.py
```

Check data freshness:
```bash
python scripts/check_nasr_staleness.py
```

## Affiliate Setup

Replace PLACEHOLDER URLs in these files with your actual affiliate links:
- `backend/affiliates.py` -- Contextual per-airport links (mountain flying, headsets, etc.)
- `frontend/index.html` -- Footer banner links (Sporty's, Amazon, etc.)

### Affiliate Programs to Sign Up For
- **Amazon Associates**: https://affiliate-program.amazon.com
- **Sporty's Pilot Shop**: https://www.sportys.com/affiliate-program
- **Gleim Aviation**: https://www.gleim.com/aviation/affiliate/
- **King Schools**: Contact via their website

## Database Schema

### airports
`icao, name, city, state, elevation_ft, tpa_ft, airspace_class, lat, lon, fuel_100ll, fuel_jeta`

### runways
`icao, rwy_id, length_ft, width_ft, surface, lighting, pattern_dir`

### frequencies
`icao, freq_type, frequency`

## Tests

```bash
pip install pytest pytest-asyncio httpx
python -m pytest backend/tests/ -v
```
