# Run with: uvicorn backend.main:app --reload --port 8000
import asyncio
from pathlib import Path
from fastapi import FastAPI, HTTPException
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import StreamingResponse, FileResponse
from fastapi.staticfiles import StaticFiles
from pydantic import BaseModel, Field, model_validator
from typing import Optional, List
import sqlite3, io

from backend.route import get_route_airports, get_multi_waypoint_airports, haversine_nm
from backend.weather import get_metars
from backend.affiliates import get_affiliates

DATA_DIR = Path(__file__).parent.parent / "data"
VERSION_FILE = DATA_DIR / "nasr_version.txt"
DB_PATH = DATA_DIR / "airports.db"

FRONTEND_DIR = Path(__file__).parent.parent / "frontend"

app = FastAPI(title="FlightStrip API")

app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],
    allow_methods=["*"],
    allow_headers=["*"],
)

@app.get("/")
async def index():
    return FileResponse(FRONTEND_DIR / "index.html")

app.mount("/static", StaticFiles(directory=str(FRONTEND_DIR)), name="static")

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
    # Multi-waypoint: list of 2-4 ICAOs  ["KBJC", "KPUB", "KGXY"]
    waypoints: Optional[List[str]] = None
    # Legacy single-segment — populated by model_validator from "from"/"to" keys
    from_field: Optional[str] = None
    to_icao: Optional[str] = None
    corridor_nm: float = 25
    mode: str = "vfr"
    exclude_heliports: bool = True
    public_only: bool = True
    min_runway_ft: int = 0

    @model_validator(mode="before")
    @classmethod
    def remap_from_to(cls, data):
        """Accept legacy {"from": ..., "to": ...} keys without Pydantic alias issues."""
        if isinstance(data, dict):
            if "from" in data and "from_field" not in data:
                data["from_field"] = data.pop("from")
            if "to" in data and "to_icao" not in data:
                data["to_icao"] = data.pop("to")
        return data

    def get_waypoints(self) -> list:
        """Resolve to a list of waypoint ICAOs regardless of input style."""
        if self.waypoints and len(self.waypoints) >= 2:
            return [w.upper() for w in self.waypoints]
        if self.from_field and self.to_icao:
            return [self.from_field.upper(), self.to_icao.upper()]
        raise ValueError("Provide either 'waypoints' list or 'from'+'to' fields")

@app.post("/route")
async def post_route(req: RouteRequest):
    try:
        wps = req.get_waypoints()
        airports = get_multi_waypoint_airports(
            wps,
            corridor_nm=req.corridor_nm,
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
        apt['affiliates'] = get_affiliates(apt, req.mode)

    # Compute total distance across all waypoints
    total_nm = 0
    wp_data = []
    conn = sqlite3.connect(str(DB_PATH))
    conn.row_factory = sqlite3.Row
    for icao in wps:
        row = conn.execute("SELECT lat, lon FROM airports WHERE icao=?", (icao,)).fetchone()
        if row:
            wp_data.append(dict(row))
    conn.close()
    for i in range(len(wp_data) - 1):
        total_nm += haversine_nm(wp_data[i]['lat'], wp_data[i]['lon'], wp_data[i+1]['lat'], wp_data[i+1]['lon'])

    route_label = " \u2192 ".join(wps)

    return {
        "route": airports,
        "waypoints": wps,
        "route_label": route_label,
        "summary": {
            "total_airports": len(airports),
            "corridor_nm": req.corridor_nm,
            "distance_nm": round(total_nm)
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
        wps = [from_icao.upper(), to_icao.upper()]
        airports = get_multi_waypoint_airports(wps, corridor_nm)
    except ValueError as e:
        raise HTTPException(status_code=404, detail=str(e))

    icao_list = [a['icao'] for a in airports]
    metars = await get_metars(icao_list)
    for apt in airports:
        apt['metar'] = metars.get(apt['icao'], {'flight_category': 'UNKNOWN', 'raw_metar': 'N/A'})

    route_label = " \u2192 ".join(wps)

    conn_dist = sqlite3.connect(str(DB_PATH))
    conn_dist.row_factory = sqlite3.Row
    total_nm = 0
    wp_coords = []
    for icao in wps:
        row = conn_dist.execute("SELECT lat, lon FROM airports WHERE icao=?", (icao,)).fetchone()
        if row:
            wp_coords.append(dict(row))
    conn_dist.close()
    for i in range(len(wp_coords) - 1):
        total_nm += haversine_nm(wp_coords[i]['lat'], wp_coords[i]['lon'],
                                  wp_coords[i+1]['lat'], wp_coords[i+1]['lon'])

    from jinja2 import Environment, FileSystemLoader
    from datetime import datetime
    template_dir = Path(__file__).parent / "templates"
    env = Environment(loader=FileSystemLoader(str(template_dir)))

    try:
        template = env.get_template("kneeboard.html")
        html_content = template.render(
            airports=airports,
            route_label=route_label,
            from_icao=from_icao,
            to_icao=to_icao,
            mode=mode,
            distance_nm=round(total_nm),
            corridor_nm=int(corridor_nm),
            generated_date=datetime.utcnow().strftime("%Y-%m-%d")
        )
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
        return StreamingResponse(
            io.BytesIO(html_content.encode()),
            media_type="text/html",
            headers={"Content-Disposition": f"attachment; filename=flightstrip_{from_icao}_{to_icao}.html",
                     "X-FlightStrip-Note": "WeasyPrint unavailable; returning HTML for browser print"}
        )

@app.post("/route/pdf")
async def post_route_pdf(req: RouteRequest):
    try:
        wps = req.get_waypoints()
        airports = get_multi_waypoint_airports(
            wps,
            corridor_nm=req.corridor_nm,
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

    route_label = " \u2192 ".join(wps)

    # Compute total route distance
    conn2 = sqlite3.connect(str(DB_PATH))
    conn2.row_factory = sqlite3.Row
    total_nm = 0
    wp_coords = []
    for icao in wps:
        row = conn2.execute("SELECT lat, lon FROM airports WHERE icao=?", (icao,)).fetchone()
        if row:
            wp_coords.append(dict(row))
    conn2.close()
    for i in range(len(wp_coords) - 1):
        total_nm += haversine_nm(wp_coords[i]['lat'], wp_coords[i]['lon'],
                                  wp_coords[i+1]['lat'], wp_coords[i+1]['lon'])

    from jinja2 import Environment, FileSystemLoader
    from datetime import datetime
    template_dir = Path(__file__).parent / "templates"
    env = Environment(loader=FileSystemLoader(str(template_dir)))

    try:
        template = env.get_template("kneeboard.html")
        html_content = template.render(
            airports=airports,
            route_label=route_label,
            from_icao=wps[0],
            to_icao=wps[-1],
            mode=req.mode,
            distance_nm=round(total_nm),
            corridor_nm=int(req.corridor_nm),
            generated_date=datetime.utcnow().strftime("%Y-%m-%d")
        )
    except Exception as e:
        raise HTTPException(status_code=500, detail=f"Template error: {e}")

    file_label = "-".join(wps)

    try:
        import weasyprint
        pdf_bytes = weasyprint.HTML(string=html_content).write_pdf()
        return StreamingResponse(
            io.BytesIO(pdf_bytes),
            media_type="application/pdf",
            headers={"Content-Disposition": f"attachment; filename={file_label}-kneeboard.pdf"}
        )
    except Exception:
        return StreamingResponse(
            io.BytesIO(html_content.encode()),
            media_type="text/html",
            headers={
                "Content-Disposition": f"attachment; filename={file_label}-kneeboard.html",
                "X-FlightStrip-Note": "WeasyPrint unavailable on this platform; open HTML in browser and Ctrl+P"
            }
        )

if __name__ == "__main__":
    import uvicorn, os
    port = int(os.environ.get("PORT", 8000))
    uvicorn.run("backend.main:app", host="0.0.0.0", port=port, reload=True)
