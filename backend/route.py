# Run with: python -c "from backend.route import get_route_airports; print(get_route_airports('KBJC','KSUN'))"
import sqlite3, math, re
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

def _abbrev_name(name: str) -> str:
    """Abbreviate airport name to max 13 chars."""
    if not name:
        return ""
    s = re.sub(r'\s+Airport\s*$', '', name, flags=re.IGNORECASE)
    replacements = [
        (r'\bRegional\b', 'Rgnl'), (r'\bMunicipal\b', 'Muni'),
        (r'\bInternational\b', 'Intl'), (r'\bExecutive\b', 'Exec'),
        (r'\bMemorial\b', 'Mem'), (r'\bNational\b', 'Natl'),
        (r'\bCounty\b', 'Cty'), (r'\bNorthern\b', 'N'),
        (r'\bSouthern\b', 'S'), (r'\bEastern\b', 'E'),
        (r'\bWestern\b', 'W'), (r'\bNorth\b', 'N'),
        (r'\bSouth\b', 'S'), (r'\bEast\b', 'E'),
        (r'\bWest\b', 'W'), (r'\bColorado\b', 'CO'),
        (r'\bMountain\b', 'Mtn'), (r'\bField\b', 'Fld'),
        (r'\bCenter\b', 'Ctr'), (r'\bMetropolitan\b', 'Metro'),
    ]
    for pattern, repl in replacements:
        s = re.sub(pattern, repl, s)
    s = re.sub(r'\s+', ' ', s).strip()
    return s[:13]

def _abbrev_city(city: str) -> str:
    """Abbreviate city name to max 10 chars."""
    if not city:
        return ""
    s = city
    replacements = [
        (r'\bFort\b', 'Ft'), (r'\bSaint\b', 'St'),
        (r'\bSprings\b', 'Spgs'), (r'\bHeights\b', 'Hts'),
        (r'\bJunction\b', 'Jct'),
    ]
    for pattern, repl in replacements:
        s = re.sub(pattern, repl, s)
    return s.strip()[:10]

def _build_pattern_display(runways: list) -> list:
    """
    Build pattern display strings from runway list.
    Returns list of strings like "08:L/26:R" or "17/35", longest runway pair first.
    """
    if not runways:
        return []

    # Filter out helipad runway IDs (H1, H2, etc.) — not standard traffic pattern runways
    runways = [r for r in runways if not re.match(r'^H\d', r.get('rwy_id', ''))]
    if not runways:
        return []

    # Sort by length descending
    sorted_rwys = sorted(runways, key=lambda r: r.get('length_ft') or 0, reverse=True)

    # Group into pairs: strip cardinal suffix (L/R/C) to find reciprocal pairs
    def base_heading(rwy_id):
        return re.sub(r'[LRC]$', '', rwy_id or '').strip()

    paired = []
    used = set()
    for rwy in sorted_rwys:
        rid = rwy.get('rwy_id', '').strip()
        if rid in used:
            continue
        # Try to find reciprocal: heading + 18 (mod 36)
        try:
            base = base_heading(rid)
            suffix = rid[len(base):]  # L, R, C, or ''
            hdg = int(base)
            recip_hdg = (hdg + 18) % 36 or 36
            recip_id = f"{recip_hdg:02d}{suffix}"
            # Also try opposite suffix for parallels
            alt_suffixes = {'L': 'R', 'R': 'L', 'C': 'C', '': ''}
            alt_recip_id = f"{recip_hdg:02d}{alt_suffixes.get(suffix, suffix)}"
        except (ValueError, TypeError):
            recip_id = None
            alt_recip_id = None

        recip = None
        for candidate in sorted_rwys:
            cid = candidate.get('rwy_id', '').strip()
            if cid not in used and cid != rid and cid in (recip_id, alt_recip_id):
                recip = candidate
                break

        if recip:
            used.add(rid)
            used.add(recip.get('rwy_id', '').strip())
            # Format: use colon notation only if pattern_dir is explicitly set and non-standard
            pat1 = rwy.get('pattern_dir', '').strip() if rwy.get('pattern_dir') else ''
            pat2 = recip.get('pattern_dir', '').strip() if recip.get('pattern_dir') else ''
            has_explicit = pat1 in ('L', 'R') or pat2 in ('L', 'R')
            if has_explicit and (pat1 == 'R' or pat2 == 'R'):
                p1 = f":{pat1}" if pat1 else ''
                p2 = f":{pat2}" if pat2 else ''
                paired.append((rwy.get('length_ft') or 0, f"{rid}{p1}/{recip.get('rwy_id','').strip()}{p2}"))
            else:
                paired.append((rwy.get('length_ft') or 0, f"{rid}/{recip.get('rwy_id','').strip()}"))
        else:
            used.add(rid)
            pat = rwy.get('pattern_dir', '').strip() if rwy.get('pattern_dir') else ''
            if pat == 'R':
                paired.append((rwy.get('length_ft') or 0, f"{rid}:R"))
            else:
                paired.append((rwy.get('length_ft') or 0, rid))

    # Sort by length desc, return just strings
    paired.sort(key=lambda x: x[0], reverse=True)
    return [s for _, s in paired]

def _get_typed_freq(frequencies: list, types: list):
    """Return first frequency matching any of the given freq_types."""
    types_upper = [t.upper() for t in types]
    for f in frequencies:
        if f.get('freq_type', '').upper() in types_upper:
            return f.get('frequency')
    return None

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

            # Computed display fields for V2C kneeboard
            rec['name_abbrev'] = _abbrev_name(rec.get('name', ''))
            rec['city_abbrev'] = _abbrev_city(rec.get('city', ''))
            rec['pattern_display'] = _build_pattern_display(rec['runways'])
            freqs = rec['frequencies']
            rec['is_towered'] = any(f.get('freq_type', '').upper() == 'TWR' for f in freqs)
            rec['freq_ctaf_tower'] = _get_typed_freq(freqs, ['TWR', 'CTAF', 'UNICOM', 'UNIC'])
            rec['freq_atis'] = _get_typed_freq(freqs, ['ATIS', 'AWOS', 'ASOS'])
            rec['freq_ground'] = _get_typed_freq(freqs, ['GND'])
            rec['freq_approach'] = _get_typed_freq(freqs, ['APP', 'APCH', 'DEP'])
            rec['freq_clearance'] = _get_typed_freq(freqs, ['CD', 'CLD', 'D-ATIS', 'CLNC DEL'])
            rec['has_ils'] = any(f.get('freq_type', '').upper() == 'ILS' for f in freqs)

            rec['metar'] = {}
            results.append(rec)

    conn.close()
    results.sort(key=lambda x: x['along_track_nm'])
    return results

def get_multi_waypoint_airports(
    waypoints: list,
    corridor_nm: float = 25,
    exclude_heliports: bool = True,
    public_only: bool = True,
    min_runway_ft: int = 0
) -> list:
    """
    Collect airports along a multi-segment route.
    waypoints: list of 2-4 ICAO strings, e.g. ["KBJC", "KPUB", "KGXY"]
    Returns deduplicated list sorted by cumulative along-track distance.
    """
    if len(waypoints) < 2:
        raise ValueError("At least 2 waypoints required")
    if len(waypoints) > 4:
        raise ValueError("Maximum 4 waypoints supported")

    seen_icaos = set()
    all_airports = []
    cumulative_nm = 0.0

    for i in range(len(waypoints) - 1):
        seg_from = waypoints[i].upper()
        seg_to = waypoints[i + 1].upper()

        seg_airports = get_route_airports(
            seg_from, seg_to, corridor_nm,
            exclude_heliports=exclude_heliports,
            public_only=public_only,
            min_runway_ft=min_runway_ft
        )

        for apt in seg_airports:
            if apt['icao'] not in seen_icaos:
                seen_icaos.add(apt['icao'])
                apt['along_track_nm'] = round(cumulative_nm + apt['along_track_nm'], 1)
                all_airports.append(apt)

        # Add segment distance to cumulative offset for next segment
        if seg_airports:
            origin = next((a for a in seg_airports if a['icao'] == seg_from), None)
            dest = next((a for a in seg_airports if a['icao'] == seg_to), None)
            if origin and dest:
                seg_nm = haversine_nm(origin['lat'], origin['lon'], dest['lat'], dest['lon'])
                cumulative_nm += seg_nm

    all_airports.sort(key=lambda x: x['along_track_nm'])
    return all_airports

def total_route_nm(waypoints_data: list) -> float:
    """Sum haversine distances between consecutive waypoints that were found."""
    total = 0.0
    for i in range(len(waypoints_data) - 1):
        a, b = waypoints_data[i], waypoints_data[i+1]
        total += haversine_nm(a['lat'], a['lon'], b['lat'], b['lon'])
    return round(total)
