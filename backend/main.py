# Run with: uvicorn backend.main:app --reload --port 8000
import asyncio
from pathlib import Path
from fastapi import FastAPI, HTTPException
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import StreamingResponse
from pydantic import BaseModel, Field
from typing import Optional
import sqlite3, io

from backend.route import get_route_airports, haversine_nm
from backend.weather import get_metars
from backend.affiliates import get_affiliates

DATA_DIR = Path(__file__).parent.parent / "data"
VERSION_FILE = DATA_DIR / "nasr_version.txt"
DB_PATH = DATA_DIR / "airports.db"

app = FastAPI(title="FlightStrip API")

app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],
    allow_methods=["*"],
    allow_headers=["*"],
)

def get_nasr_version():
    try:
        return VERSION_FILE.read_text().strip()
    except:
        return "unknown"

@app.on_event("startup")
async def startup():
    from backend.staleness import check_staleness
    check_staleness()

@app.get("/health")
async def health():
    return {"status": "ok", "nasr_version": get_nasr_version()}

@app.get("/airport/{icao}")
async def get_airport(icao: str):
    icao = icao.upper()
    conn = sqlite3.connect(DB_PATH)
    conn.row_factory = sqlite3.Row
    apt = conn.execute("SELECT * FROM airports WHERE icao=?", (icao,)).fetchone()
    if not apt:
        conn.close()
        raise HTTPException(status_code=404, detail=f"Airport {icao} not found")
    rec = dict(apt)
    rec['runways'] = [dict(r) for r in conn.execute(
        "SELECT * FROM runways WHERE icao=?", (icao,)
    ).fetchall()]
    rec['frequencies'] = [dict(f) for f in conn.execute(
        "SELECT * FROM frequencies WHERE icao=?", (icao,)
    ).fetchall()]
    conn.close()
    metars = await get_metars([icao])
    rec['metar'] = metars.get(icao, {})
    return rec

class RouteRequest(BaseModel):
    from_field: str = Field(alias="from")
    to_icao: str = Field(alias="to")
    corridor_nm: float = 25
    mode: str = "vfr"
    exclude_heliports: bool = True
    public_only: bool = True
    min_runway_ft: int = 0

    model_config = {"populate_by_name": True}

@app.post("/route")
async def post_route(req: RouteRequest):
    try:
        airports = get_route_airports(
            req.from_field, req.to_icao, req.corridor_nm,
            exclude_heliports=req.exclude_heliports,
            public_only=req.public_only,
            min_runway_ft=req.min_runway_ft
        )
    except ValueError as e:
        raise HTTPException(status_code=404, detail=str(e))

    icao_list = [a['icao'] for a in airports]
    metars = await get_metars(icao_list)

    vfr_freq_types = {'CTAF','UNICOM','ATIS','AWOS','ASOS','TWR','GND'}

    for apt in airports:
        apt['metar'] = metars.get(apt['icao'], {'flight_category': 'UNKNOWN', 'raw_metar': 'N/A'})
        apt['affiliates'] = get_affiliates(apt, req.mode)
        if req.mode == 'vfr' or req.mode == 'student':
            apt['frequencies'] = [f for f in apt['frequencies'] if f['freq_type'].upper() in vfr_freq_types]

    origin = airports[0] if airports else None
    dest = airports[-1] if airports else None
    total_nm = 0
    if origin and dest:
        total_nm = round(haversine_nm(origin['lat'], origin['lon'], dest['lat'], dest['lon']))

    return {
        "route": airports,
        "summary": {
            "total_airports": len(airports),
            "corridor_nm": req.corridor_nm,
            "distance_nm": total_nm
        }
    }

@app.get("/route/pdf")
async def route_pdf(
    from_icao: str,
    to_icao: str,
    corridor_nm: float = 25,
    mode: str = "vfr"
):
    try:
        airports = get_route_airports(from_icao, to_icao, corridor_nm)
    except ValueError as e:
        raise HTTPException(status_code=404, detail=str(e))

    icao_list = [a['icao'] for a in airports]
    metars = await get_metars(icao_list)
    for apt in airports:
        apt['metar'] = metars.get(apt['icao'], {'flight_category': 'UNKNOWN', 'raw_metar': 'N/A'})

    from jinja2 import Environment, FileSystemLoader
    template_dir = Path(__file__).parent / "templates"
    env = Environment(loader=FileSystemLoader(str(template_dir)))

    try:
        template = env.get_template("kneeboard.html")
        html_content = template.render(airports=airports, from_icao=from_icao, to_icao=to_icao, mode=mode)
    except Exception as e:
        raise HTTPException(status_code=500, detail=f"Template error: {e}")

    try:
        import weasyprint
        pdf_bytes = weasyprint.HTML(string=html_content).write_pdf()
        return StreamingResponse(
            io.BytesIO(pdf_bytes),
            media_type="application/pdf",
            headers={"Content-Disposition": f"attachment; filename=flightstrip_{from_icao}_{to_icao}.pdf"}
        )
    except Exception:
        # WeasyPrint not available or missing system libs -- return HTML with print CSS
        return StreamingResponse(
            io.BytesIO(html_content.encode()),
            media_type="text/html",
            headers={"Content-Disposition": f"attachment; filename=flightstrip_{from_icao}_{to_icao}.html",
                     "X-FlightStrip-Note": "WeasyPrint unavailable; returning HTML for browser print"}
        )

@app.post("/route/pdf")
async def post_route_pdf(req: RouteRequest):
    try:
        airports = get_route_airports(
            req.from_field, req.to_icao, req.corridor_nm,
            exclude_heliports=req.exclude_heliports,
            public_only=req.public_only,
            min_runway_ft=req.min_runway_ft
        )
    except ValueError as e:
        raise HTTPException(status_code=404, detail=str(e))

    icao_list = [a['icao'] for a in airports]
    metars = await get_metars(icao_list)
    for apt in airports:
        apt['metar'] = metars.get(apt['icao'], {'flight_category': 'UNKNOWN', 'raw_metar': 'N/A'})

    from jinja2 import Environment, FileSystemLoader
    from datetime import datetime
    template_dir = Path(__file__).parent / "templates"
    env = Environment(loader=FileSystemLoader(str(template_dir)))

    try:
        template = env.get_template("kneeboard.html")
        html_content = template.render(
            airports=airports,
            from_icao=req.from_field.upper(),
            to_icao=req.to_icao.upper(),
            mode=req.mode,
            generated_date=datetime.utcnow().strftime("%Y-%m-%d %H:%M UTC")
        )
    except Exception as e:
        raise HTTPException(status_code=500, detail=f"Template error: {e}")

    try:
        import weasyprint
        pdf_bytes = weasyprint.HTML(string=html_content).write_pdf()
        return StreamingResponse(
            io.BytesIO(pdf_bytes),
            media_type="application/pdf",
            headers={"Content-Disposition": f"attachment; filename={req.from_field}-{req.to_icao}-kneeboard.pdf"}
        )
    except Exception:
        return StreamingResponse(
            io.BytesIO(html_content.encode()),
            media_type="text/html",
            headers={
                "Content-Disposition": f"attachment; filename={req.from_field}-{req.to_icao}-kneeboard.html",
                "X-FlightStrip-Note": "WeasyPrint unavailable on this platform; open HTML in browser and Ctrl+P"
            }
        )

if __name__ == "__main__":
    import uvicorn, os
    port = int(os.environ.get("PORT", 8000))
    uvicorn.run("backend.main:app", host="0.0.0.0", port=port, reload=True)
