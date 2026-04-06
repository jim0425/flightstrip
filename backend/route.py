# Run with: python -c "from backend.route import get_route_airports; print(get_route_airports('KBJC','KSUN'))"
import sqlite3, math
from pathlib import Path
from typing import Optional

DB_PATH = Path(__file__).parent.parent / "data" / "airports.db"

def nm_to_km(nm: float) -> float:
    return nm * 1.852

def haversine_nm(lat1, lon1, lat2, lon2) -> float:
    """Distance in nautical miles between two lat/lon points."""
    R = 3440.065  # Earth radius in NM
    phi1, phi2 = math.radians(lat1), math.radians(lat2)
    dphi = math.radians(lat2 - lat1)
    dlam = math.radians(lon2 - lon1)
    a = math.sin(dphi/2)**2 + math.cos(phi1)*math.cos(phi2)*math.sin(dlam/2)**2
    return 2 * R * math.asin(math.sqrt(a))

def cross_track_nm(lat, lon, lat1, lon1, lat2, lon2) -> float:
    """Approximate cross-track distance from point (lat,lon) to segment (lat1,lon1)-(lat2,lon2)."""
    dx = lat2 - lat1
    dy = lon2 - lon1
    if dx == 0 and dy == 0:
        return haversine_nm(lat, lon, lat1, lon1)
    t = ((lat - lat1)*dx + (lon - lon1)*dy) / (dx*dx + dy*dy)
    t = max(0.0, min(1.0, t))
    closest_lat = lat1 + t*dx
    closest_lon = lon1 + t*dy
    return haversine_nm(lat, lon, closest_lat, closest_lon)

def along_track_nm(lat, lon, lat1, lon1, lat2, lon2) -> float:
    """Distance from departure (lat1,lon1) to projection of point onto route."""
    dx = lat2 - lat1
    dy = lon2 - lon1
    if dx == 0 and dy == 0:
        return 0.0
    t = ((lat - lat1)*dx + (lon - lon1)*dy) / (dx*dx + dy*dy)
    t = max(0.0, min(1.0, t))
    proj_lat = lat1 + t*dx
    proj_lon = lon1 + t*dy
    return haversine_nm(lat1, lon1, proj_lat, proj_lon)

def get_route_airports(
    from_icao: str,
    to_icao: str,
    corridor_nm: float = 25,
    exclude_heliports: bool = True,
    public_only: bool = True,
    min_runway_ft: int = 0
) -> list:
    conn = sqlite3.connect(DB_PATH)
    conn.row_factory = sqlite3.Row

    origin = conn.execute("SELECT * FROM airports WHERE icao=?", (from_icao.upper(),)).fetchone()
    dest = conn.execute("SELECT * FROM airports WHERE icao=?", (to_icao.upper(),)).fetchone()

    if not origin or not dest:
        conn.close()
        raise ValueError(f"Airport not found: {from_icao if not origin else to_icao}")

    lat1, lon1 = origin['lat'], origin['lon']
    lat2, lon2 = dest['lat'], dest['lon']

    # Bounding box with padding
    pad = corridor_nm / 60.0
    min_lat = min(lat1, lat2) - pad
    max_lat = max(lat1, lat2) + pad
    min_lon = min(lon1, lon2) - pad
    max_lon = max(lon1, lon2) + pad

    filters = ["lat BETWEEN ? AND ? AND lon BETWEEN ? AND ?"]
    params = [min_lat, max_lat, min_lon, max_lon]

    if exclude_heliports:
        filters.append("(site_type IS NULL OR site_type != 'H')")
    if public_only:
        filters.append("(apt_type IS NULL OR apt_type = 'PU' OR apt_type = 'MA')")

    sql = f"SELECT * FROM airports WHERE {' AND '.join(filters)}"
    candidates = conn.execute(sql, params).fetchall()

    results = []
    for apt in candidates:
        ct = cross_track_nm(apt['lat'], apt['lon'], lat1, lon1, lat2, lon2)
        if ct <= corridor_nm:
            at = along_track_nm(apt['lat'], apt['lon'], lat1, lon1, lat2, lon2)
            rec = dict(apt)
            rec['cross_track_nm'] = round(ct, 1)
            rec['along_track_nm'] = round(at, 1)

            # Attach runways
            rec['runways'] = [dict(r) for r in conn.execute(
                "SELECT rwy_id, length_ft, width_ft, surface, lighting, pattern_dir FROM runways WHERE icao=?",
                (apt['icao'],)
            ).fetchall()]

            # Attach frequencies
            rec['frequencies'] = [dict(f) for f in conn.execute(
                "SELECT freq_type, frequency FROM frequencies WHERE icao=?",
                (apt['icao'],)
            ).fetchall()]

            # Max runway length and kneeboard inclusion flag
            max_rwy = max((r['length_ft'] for r in rec['runways']), default=0)
            rec['max_rwy_length'] = max_rwy

            # Skip airports below min_runway_ft threshold
            if min_runway_ft > 0 and max_rwy < min_runway_ft:
                # Always include origin and destination
                if apt['icao'] not in (from_icao.upper(), to_icao.upper()):
                    continue

            rec['kneeboard_include'] = (
                rec.get('apt_type') in ('PU', 'MA', None) and
                rec.get('site_type', 'A') == 'A' and
                max_rwy >= 1500
            ) or apt['icao'] in (from_icao.upper(), to_icao.upper())

            rec['metar'] = {}
            results.append(rec)

    conn.close()
    results.sort(key=lambda x: x['along_track_nm'])
    return results
