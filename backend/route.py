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
    s = name.title()
    s = re.sub(r'\s+Airport\s*$', '', s, flags=re.IGNORECASE)
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
    s = city.title()
    replacements = [
        (r'\bFort\b', 'Ft'), (r'\bSaint\b', 'St'),
        (r'\bSprings\b', 'Spgs'), (r'\bHeights\b', 'Hts'),
        (r'\bJunction\b', 'Jct'),
    ]
    for pattern, repl in replacements:
        s = re.sub(pattern, repl, s)
    return s.strip()[:10]

_PAVED_SURFACES = ('ASPH', 'CONC', 'HARD', 'PEM', 'PFC', 'MACA', 'TARMAC', 'BITU', 'MACADAM')

def _calc_kboard_lines(rec: dict, apch_lines: list) -> int:
    """
    Estimate visual line count for a kneeboard row.
    Notes column: col.cco = 69px wide, 2px padding each side → 63px usable.
    8.5px Arial ≈ 4.5px/char average → ~14 chars per line.
    Counts all visible note segments: CW, Pref, Dirt runways, and approach lines.
    Minimum 3 lines per airport (ICAO + Name stack always 3 tall).
    """
    _CPL = 14  # chars per line in Notes column

    notes_segs = []
    if rec.get('calm_wind_runway'):
        notes_segs.append('CW: ' + rec['calm_wind_runway'])
    if rec.get('preferred_runway'):
        notes_segs.append('Pref: ' + rec['preferred_runway'])

    dirt = [r.get('rwy_id', '') for r in rec.get('runways', [])
            if not any((r.get('surface') or '').upper().startswith(p) for p in _PAVED_SURFACES)]
    if dirt:
        notes_segs.append('Dirt: ' + ', '.join(dirt))

    notes_segs.extend(apch_lines)

    notes_vis = sum(max(1, (len(s) + _CPL - 1) // _CPL) for s in notes_segs) if notes_segs else 0
    rwy_vis = len(rec.get('runways', []))
    pat_vis = len(rec.get('pattern_display', []))

    return max(3, rwy_vis, pat_vis, notes_vis)

def _get_right_pattern_set(runways: list) -> set:
    """
    Parse compound pattern_dir strings (e.g. '10:R 28:R') across all runways
    to return set of rwy_ids (uppercase) that have published right-hand pattern.
    NASR stores the full airport pattern string on every runway row.
    """
    right_rwys = set()
    for rwy in runways:
        pd = (rwy.get('pattern_dir') or '').strip()
        if not pd or pd.upper() == 'STD':
            continue
        for token in pd.split():
            parts = token.split(':')
            if len(parts) == 2 and parts[1].strip().upper() == 'R':
                right_rwys.add(parts[0].strip().upper())
    return right_rwys


def _build_pattern_display(runways: list) -> list:
    """
    Build pattern display strings from runway list.
    Handles both individual runway rows (rwy_id='07L') and NASR combined-pair rows
    (rwy_id='07L/25R'). When the DB stores a combined pair, split it and format each end.

    Format rules:
      - All-standard pair (both left): '17/35'
      - Non-standard pair: '10:R/28L'  (right gets :R, partner gets L suffix)
      - Both right:        '10:R/28:R'
      - Unpaired standard: '10'
      - Unpaired right:    '10:R'
    Returns list sorted longest runway pair first.
    """
    if not runways:
        return []

    # Filter out helipad runway IDs (H1, H2, etc.)
    runways = [r for r in runways if not re.match(r'^H\d', r.get('rwy_id', ''))]
    if not runways:
        return []

    right_set = _get_right_pattern_set(runways)

    def fmt_end(end_id: str, partner_is_right: bool = False) -> str:
        """Format a single runway-end id with pattern indicator."""
        is_right = end_id.upper() in right_set
        if is_right:
            return f"{end_id}:R"
        elif partner_is_right and not re.search(r'[LRC]$', end_id):
            # Only append L suffix on plain numeric ends (not already-labeled parallels)
            return f"{end_id}L"
        return end_id

    sorted_rwys = sorted(runways, key=lambda r: r.get('length_ft') or 0, reverse=True)
    paired = []
    used = set()

    for rwy in sorted_rwys:
        rid = rwy.get('rwy_id', '').strip()
        if rid in used:
            continue
        used.add(rid)

        length = rwy.get('length_ft') or 0

        # NASR combined format: '07L/25R', '15/33', etc.
        if '/' in rid:
            parts = rid.split('/', 1)
            e1, e2 = parts[0].strip(), parts[1].strip()
            r1_right = e1.upper() in right_set
            r2_right = e2.upper() in right_set
            if r1_right or r2_right:
                s1 = fmt_end(e1, partner_is_right=r2_right)
                s2 = fmt_end(e2, partner_is_right=r1_right)
                paired.append((length, f"{s1}/{s2}"))
            else:
                paired.append((length, f"{e1}/{e2}"))
        else:
            # Individual end row — try to pair with reciprocal in this list
            def base_heading(rwy_id):
                return re.sub(r'[LRC]$', '', rwy_id or '').strip()
            try:
                base = base_heading(rid)
                suffix = rid[len(base):]
                hdg = int(base)
                recip_hdg = (hdg + 18) % 36 or 36
                recip_id = f"{recip_hdg:02d}{suffix}"
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
                recip_id_str = recip.get('rwy_id', '').strip()
                used.add(recip_id_str)
                r1_right = rid.upper() in right_set
                r2_right = recip_id_str.upper() in right_set
                if r1_right or r2_right:
                    s1 = fmt_end(rid, partner_is_right=r2_right)
                    s2 = fmt_end(recip_id_str, partner_is_right=r1_right)
                    paired.append((length, f"{s1}/{s2}"))
                else:
                    paired.append((length, f"{rid}/{recip_id_str}"))
            else:
                paired.append((length, fmt_end(rid)))

    paired.sort(key=lambda x: x[0], reverse=True)
    return [s for _, s in paired]

def _get_typed_freq(frequencies: list, types: list):
    """Return first frequency matching any of the given freq_types (exact or prefix match)."""
    types_upper = [t.upper() for t in types]
    for f in frequencies:
        ft = f.get('freq_type', '').upper()
        if ft in types_upper or any(ft.startswith(t) for t in types_upper):
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
    # Always exclude Class B airports (major commercial hubs)
    filters.append("(airspace_class IS NULL OR airspace_class != 'B')")

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

            # Instrument approaches from d-TPP (grouped by runway, abbreviated types)
            apch_rows = conn.execute(
                "SELECT rwy_end, approach_type FROM approaches WHERE icao=? ORDER BY rwy_end, approach_type",
                (apt['icao'],)
            ).fetchall()

            # Abbreviate verbose type names
            _APCH_ABBREV = {
                'RNAV (GPS)': 'RNAV', 'RNAV (RNP)': 'RNP',
                'ILS OR LOC': 'ILS/LOC', 'ILS Z OR LOC': 'ILS/LOC', 'ILS Y OR LOC': 'ILS/LOC',
                'ILS X OR LOC': 'ILS/LOC', 'HI-ILS OR LOC': 'Hi-ILS', 'ILS OR LOC/DME': 'ILS/LOC',
                'HI-ILS OR LOC/DME': 'Hi-ILS', 'HI-ILS Y OR LOC': 'Hi-ILS',
                'ILS Z OR LOC/DME': 'ILS/LOC', 'ILS Y OR LOC/DME': 'ILS/LOC',
                'VOR/DME': 'VOR/D', 'VOR OR TACAN': 'VOR/TAC', 'VOR/DME OR TACAN': 'VOR/D',
                'LOC BC': 'LOC-BC', 'COPTER RNAV (GPS)': 'COPTER', 'COPTER RNAV (RNP)': 'COPTER',
                'HI-TACAN': 'Hi-TAC',
            }
            def _abbrev_apch(t: str) -> str:
                if t in _APCH_ABBREV:
                    return _APCH_ABBREV[t]
                if 'VISUAL' in t:
                    return 'VISUAL'
                if t.startswith('COPTER'):
                    return 'COPTER'
                return t

            # Group by runway end, collect unique abbreviated types
            from collections import OrderedDict
            rwy_types: dict = OrderedDict()
            for rwy_end, apch_type in apch_rows:
                abbrev = _abbrev_apch(apch_type)
                # Circling-only approaches have no runway end — group them under
                # "Circling" rather than dropping them (they're real approaches).
                key = 'Circling' if rwy_end == 'CIRC' else rwy_end
                if key not in rwy_types:
                    rwy_types[key] = []
                if abbrev not in rwy_types[key]:
                    rwy_types[key].append(abbrev)

            # Format: "30R ILS/LOC, RNAV" per line (HTML <br> for template)
            apch_lines = [f"{rwy} {', '.join(types)}" for rwy, types in rwy_types.items()]
            rec['approach_notes'] = '<br>'.join(apch_lines)
            rec['calm_wind_runway'] = ''
            rec['preferred_runway'] = ''

            # Pre-compute kboard_lines: visual line count including text-wrapping simulation.
            rec['kboard_lines'] = _calc_kboard_lines(rec, apch_lines)

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
