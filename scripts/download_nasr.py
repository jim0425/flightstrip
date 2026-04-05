# Run with: python scripts/download_nasr.py
import os, re, sqlite3, zipfile, io, requests
from pathlib import Path

DATA_DIR = Path(__file__).parent.parent / "data"
DB_PATH = DATA_DIR / "airports.db"
VERSION_FILE = DATA_DIR / "nasr_version.txt"
NASR_ZIP = DATA_DIR / "nasr_raw" / "nasr.zip"

def find_current_nasr_url():
    """Scrape the FAA NASR subscription page to find current cycle URL."""
    index_url = "https://www.faa.gov/air_traffic/flight_info/aeronav/aero_data/NASR_Subscription/"
    resp = requests.get(index_url, timeout=30)
    resp.raise_for_status()
    matches = re.findall(r'href="([^"]*28DaySubscription[^"]*\.zip)"', resp.text)
    if not matches:
        matches = re.findall(r'(https?://[^\s"]*28Day[^\s"]*\.zip)', resp.text)
    if matches:
        url = matches[0]
        if not url.startswith('http'):
            url = 'https://nfdc.faa.gov' + url
        return url
    from datetime import date, timedelta
    today = date.today()
    base = "https://nfdc.faa.gov/webContent/28DaySub/"
    for attempt in range(4):
        d = today - timedelta(days=attempt*7)
        date_str = d.strftime("%Y-%m-%d")
        url = f"{base}28DaySubscription_Effective_{date_str}.zip"
        try:
            r = requests.head(url, timeout=10)
            if r.status_code == 200:
                return url
        except:
            pass
    raise RuntimeError("Could not find current NASR zip URL")

def parse_formatted_latlon(s):
    """Parse formatted lat/lon like '39-54-31.7000N' or '105-07-01.9000W' to decimal degrees."""
    if not s or len(s) < 7:
        return None
    try:
        s = s.strip()
        direction = s[-1]
        if direction not in 'NSEW':
            return None
        parts = s[:-1].split('-')
        if len(parts) != 3:
            return None
        dd = int(parts[0])
        mm = int(parts[1])
        ss = float(parts[2])
        val = dd + mm/60 + ss/3600
        if direction in 'SW':
            val = -val
        return round(val, 6)
    except (ValueError, IndexError):
        return None

def parse_apt_record(line):
    """Parse APT record from APT.txt (NASR fixed-width format).

    Field positions (1-indexed in FAA docs, 0-indexed here):
    - Record type: [0:3] = 'APT'
    - Site number: [3:14]
    - FAA LID: [27:31]
    - State: [48:50]
    - City: [93:133]
    - Name: [133:183]
    - Lat formatted: [523:538] (DD-MM-SS.SSSSN)
    - Lon formatted: [550:565] (DDD-MM-SS.SSSSW)
    - Elevation: [578:585]
    - TPA (AGL): [593:597]
    - Fuel types: [900:940]
    - ICAO identifier: [1210:1217]
    """
    if not line.startswith('APT'):
        return None
    if len(line) < 600:
        return None
    try:
        site_num = line[3:14].strip()
        faa_lid = line[27:31].strip()
        if not faa_lid or len(faa_lid) < 2:
            return None

        state = line[48:50].strip()
        city = line[93:133].strip()
        name = line[133:183].strip()

        lat_str = line[523:538].strip()
        lon_str = line[550:565].strip()
        lat = parse_formatted_latlon(lat_str)
        lon = parse_formatted_latlon(lon_str)
        if lat is None or lon is None:
            return None

        elev_str = line[578:585].strip()
        elev = int(float(elev_str)) if elev_str else 0

        tpa_str = line[593:597].strip() if len(line) > 597 else ''
        tpa = int(tpa_str) if tpa_str.isdigit() else None
        # TPA in NASR is AGL; total pattern altitude = elev + tpa
        if tpa is not None:
            tpa = elev + tpa

        fuel_str = line[900:940].strip() if len(line) > 940 else ''
        fuel_100ll = 1 if '100LL' in fuel_str else 0
        fuel_jeta = 1 if 'JET' in fuel_str.upper() else 0

        # ICAO identifier at position 1210 (7 chars)
        icao = line[1210:1217].strip() if len(line) > 1217 else ''
        if not icao:
            # Build ICAO from FAA LID for US airports
            if len(faa_lid) == 3 and faa_lid.isalpha():
                icao = 'K' + faa_lid
            else:
                icao = faa_lid

        return {
            'site_num': site_num,
            'icao': icao, 'name': name, 'city': city, 'state': state,
            'elevation_ft': elev, 'tpa_ft': tpa, 'airspace_class': '',
            'lat': lat, 'lon': lon, 'fuel_100ll': fuel_100ll, 'fuel_jeta': fuel_jeta
        }
    except (ValueError, IndexError):
        return None

def parse_rwy_record(line):
    """Parse RWY record from APT.txt.

    Field positions (0-indexed):
    - Record type: [0:3] = 'RWY'
    - Site number: [3:14]
    - Runway ID: [16:23]
    - Length: [23:28]
    - Width: [28:32]
    - Surface: [32:44]
    - Edge lights: [60:65]
    - Base end ID: [65:68]
    - Base right traffic: [81:82] (Y/N)
    - Reciprocal end ID: [287:290]
    - Reciprocal right traffic: [303:304]
    """
    if not line.startswith('RWY'):
        return None
    if len(line) < 100:
        return None
    try:
        site_num = line[3:14].strip()
        rwy_id = line[16:23].strip()
        if not rwy_id:
            return None

        length_str = line[23:28].strip()
        width_str = line[28:32].strip()
        surface = line[32:44].strip()
        lighting = line[60:65].strip()

        length = int(length_str) if length_str.isdigit() else 0
        width = int(width_str) if width_str.isdigit() else 0

        # Determine traffic pattern direction
        base_rt = line[81:82].strip() if len(line) > 82 else ''
        recip_rt = line[303:304].strip() if len(line) > 304 else ''

        # Build pattern info: base end gets 'R' if right traffic, else 'L'
        base_end = line[65:68].strip()
        recip_end = line[287:290].strip() if len(line) > 290 else ''
        pattern_info = ''
        if base_end and base_rt == 'Y':
            pattern_info += f'{base_end}:R '
        if recip_end and recip_rt == 'Y':
            pattern_info += f'{recip_end}:R'
        pattern_info = pattern_info.strip() if pattern_info.strip() else 'STD'

        return {
            'site_num': site_num,
            'rwy_id': rwy_id, 'length_ft': length,
            'width_ft': width, 'surface': surface, 'lighting': lighting,
            'pattern_dir': pattern_info
        }
    except (ValueError, IndexError):
        return None

def parse_twr3_record(line):
    """Parse TWR3 record for frequencies.

    TWR3 has up to 9 frequency/use pairs:
    - [4:8] = identifier (FAA LID)
    - [8:52] = frequency(1), [52:102] = use(1)
    - [102:146] = frequency(2), [146:196] = use(2)
    - etc. each pair is 44+50=94 chars
    """
    if not line.startswith('TWR3'):
        return None
    try:
        faa_lid = line[4:8].strip()
        if not faa_lid:
            return None

        results = []
        # Parse up to 9 frequency/use pairs
        offsets = [
            (8, 52, 102),     # freq1 start, use start, next pair
            (102, 146, 196),
            (196, 240, 290),
            (290, 334, 384),
            (384, 428, 478),
            (478, 522, 572),
            (572, 616, 666),
            (666, 710, 760),
            (760, 804, 854),
        ]
        for freq_start, use_start, _ in offsets:
            if len(line) <= use_start:
                break
            freq_raw = line[freq_start:use_start].strip()
            use_raw = line[use_start:use_start+50].strip() if len(line) > use_start+50 else line[use_start:].strip()
            if not freq_raw:
                continue

            # Extract the numeric frequency
            freq_match = re.search(r'(\d{2,3}\.\d+)', freq_raw)
            if not freq_match:
                continue
            frequency = freq_match.group(1)

            # Parse use type
            freq_type = categorize_freq_use(use_raw)

            results.append({
                'faa_lid': faa_lid,
                'freq_type': freq_type,
                'frequency': frequency
            })

        return results if results else None
    except (ValueError, IndexError):
        return None

def parse_twr8_record(line):
    """Parse TWR8 record for airspace class.

    - [4:8] = identifier
    - [8] = Class B (Y/blank)
    - [9] = Class C
    - [10] = Class D
    - [11] = Class E
    """
    if not line.startswith('TWR8'):
        return None
    try:
        faa_lid = line[4:8].strip()
        if not faa_lid:
            return None
        class_b = line[8:9].strip() == 'Y' if len(line) > 8 else False
        class_c = line[9:10].strip() == 'Y' if len(line) > 9 else False
        class_d = line[10:11].strip() == 'Y' if len(line) > 10 else False
        class_e = line[11:12].strip() == 'Y' if len(line) > 11 else False

        if class_b:
            airspace = 'B'
        elif class_c:
            airspace = 'C'
        elif class_d:
            airspace = 'D'
        elif class_e:
            airspace = 'E'
        else:
            airspace = ''

        return {'faa_lid': faa_lid, 'airspace_class': airspace}
    except (ValueError, IndexError):
        return None

def categorize_freq_use(use_str):
    """Categorize frequency use string into standard type."""
    u = use_str.upper()
    if 'ATIS' in u:
        return 'ATIS'
    if 'AWOS' in u:
        return 'AWOS'
    if 'ASOS' in u:
        return 'ASOS'
    if 'GND' in u or 'GROUND' in u:
        return 'GND'
    if 'CTAF' in u or 'C/P' in u:
        return 'CTAF'
    if 'UNIC' in u:
        return 'UNICOM'
    if 'LCL' in u or 'TWR' in u:
        return 'TWR'
    if 'APCH' in u or 'APP' in u:
        return 'APCH'
    if 'DEP' in u:
        return 'DEP'
    if 'CD' in u or 'CLNC' in u or 'CLR' in u:
        return 'CD'
    return use_str[:10].strip() if use_str else 'OTHER'

def create_db(conn):
    conn.executescript("""
        CREATE TABLE IF NOT EXISTS airports (
            icao TEXT PRIMARY KEY, name TEXT, city TEXT, state TEXT,
            elevation_ft INT, tpa_ft INT, airspace_class TEXT,
            lat REAL, lon REAL, fuel_100ll INT, fuel_jeta INT
        );
        CREATE TABLE IF NOT EXISTS runways (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            icao TEXT, rwy_id TEXT, length_ft INT, width_ft INT,
            surface TEXT, lighting TEXT, pattern_dir TEXT
        );
        CREATE TABLE IF NOT EXISTS frequencies (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            icao TEXT, freq_type TEXT, frequency TEXT
        );
    """)
    conn.commit()

def main():
    DATA_DIR.mkdir(exist_ok=True)

    # Check for cached zip
    if NASR_ZIP.exists():
        print(f"Using cached NASR zip: {NASR_ZIP} ({NASR_ZIP.stat().st_size/1024/1024:.1f} MB)")
        zip_data = NASR_ZIP.read_bytes()
    else:
        print("Finding current NASR cycle URL...")
        try:
            nasr_url = find_current_nasr_url()
            print(f"Downloading NASR from: {nasr_url}")
            resp = requests.get(nasr_url, timeout=300, stream=True)
            resp.raise_for_status()
            zip_data = resp.content
            print(f"Downloaded {len(zip_data)/1024/1024:.1f} MB")
            # Cache it
            NASR_ZIP.parent.mkdir(parents=True, exist_ok=True)
            NASR_ZIP.write_bytes(zip_data)
        except Exception as e:
            print(f"ERROR downloading NASR: {e}")
            print("Creating minimal test database with known airports...")
            create_minimal_db()
            return

    # Delete old DB
    if DB_PATH.exists():
        DB_PATH.unlink()

    conn = sqlite3.connect(DB_PATH)
    create_db(conn)

    airports_loaded = 0
    runways_loaded = 0
    freqs_loaded = 0

    # Build site_num -> ICAO mapping from APT records
    site_to_icao = {}
    # Also build faa_lid -> ICAO mapping for TWR lookups
    lid_to_icao = {}

    with zipfile.ZipFile(io.BytesIO(zip_data)) as zf:
        names = zf.namelist()
        print(f"ZIP contains {len(names)} files")

        # === PASS 1: Parse APT records and RWY records from APT.txt ===
        print("Parsing APT.txt (airports + runways)...")
        rwy_buffer = []  # Store RWY records to insert after we have the mapping
        with zf.open('APT.txt') as f:
            for raw_line in f:
                try:
                    line = raw_line.decode('latin-1')
                except:
                    continue

                if line.startswith('APT'):
                    rec = parse_apt_record(line)
                    if rec:
                        site_to_icao[rec['site_num']] = rec['icao']
                        faa_lid = line[27:31].strip()
                        lid_to_icao[faa_lid] = rec['icao']
                        try:
                            conn.execute(
                                "INSERT OR REPLACE INTO airports VALUES (?,?,?,?,?,?,?,?,?,?,?)",
                                (rec['icao'], rec['name'], rec['city'], rec['state'],
                                 rec['elevation_ft'], rec['tpa_ft'], rec['airspace_class'],
                                 rec['lat'], rec['lon'], rec['fuel_100ll'], rec['fuel_jeta'])
                            )
                            airports_loaded += 1
                        except sqlite3.Error:
                            pass

                elif line.startswith('RWY'):
                    rec = parse_rwy_record(line)
                    if rec:
                        rwy_buffer.append(rec)

        # Insert RWY records with ICAO lookup
        print(f"Inserting {len(rwy_buffer)} runway records...")
        for rec in rwy_buffer:
            icao = site_to_icao.get(rec['site_num'])
            if not icao:
                continue
            try:
                conn.execute(
                    "INSERT INTO runways (icao,rwy_id,length_ft,width_ft,surface,lighting,pattern_dir) VALUES (?,?,?,?,?,?,?)",
                    (icao, rec['rwy_id'], rec['length_ft'], rec['width_ft'],
                     rec['surface'], rec['lighting'], rec['pattern_dir'])
                )
                runways_loaded += 1
            except sqlite3.Error:
                pass

        # === PASS 2: Parse TWR.txt for frequencies and airspace class ===
        print("Parsing TWR.txt (frequencies + airspace)...")
        with zf.open('TWR.txt') as f:
            for raw_line in f:
                try:
                    line = raw_line.decode('latin-1')
                except:
                    continue

                if line.startswith('TWR3'):
                    records = parse_twr3_record(line)
                    if records:
                        for rec in records:
                            icao = lid_to_icao.get(rec['faa_lid'])
                            if not icao:
                                # Try with K prefix
                                icao = lid_to_icao.get(rec['faa_lid']) or ('K' + rec['faa_lid'] if len(rec['faa_lid']) == 3 else rec['faa_lid'])
                            try:
                                conn.execute(
                                    "INSERT INTO frequencies (icao,freq_type,frequency) VALUES (?,?,?)",
                                    (icao, rec['freq_type'], rec['frequency'])
                                )
                                freqs_loaded += 1
                            except sqlite3.Error:
                                pass

                elif line.startswith('TWR8'):
                    rec = parse_twr8_record(line)
                    if rec and rec['airspace_class']:
                        icao = lid_to_icao.get(rec['faa_lid'])
                        if icao:
                            try:
                                conn.execute(
                                    "UPDATE airports SET airspace_class=? WHERE icao=?",
                                    (rec['airspace_class'], icao)
                                )
                            except sqlite3.Error:
                                pass

    conn.execute("CREATE INDEX IF NOT EXISTS idx_airports_lat_lon ON airports(lat, lon)")
    conn.execute("CREATE INDEX IF NOT EXISTS idx_runways_icao ON runways(icao)")
    conn.execute("CREATE INDEX IF NOT EXISTS idx_frequencies_icao ON frequencies(icao)")
    conn.commit()

    from datetime import date
    VERSION_FILE.write_text(date.today().isoformat())

    print(f"\nLoaded {airports_loaded} airports, {runways_loaded} runways, {freqs_loaded} frequencies")

    # Verify key airports exist
    for icao in ['KBJC', 'KSUN', 'KDEN']:
        row = conn.execute("SELECT icao, name, lat, lon, airspace_class FROM airports WHERE icao=?", (icao,)).fetchone()
        print(f"  {icao}: {row}")

    # Show runway sample
    rwy = conn.execute("SELECT * FROM runways WHERE icao='KBJC'").fetchall()
    print(f"  KBJC runways: {len(rwy)}")

    # Show freq sample
    freq = conn.execute("SELECT * FROM frequencies WHERE icao='KBJC'").fetchall()
    print(f"  KBJC frequencies: {len(freq)}")

    conn.close()

def create_minimal_db():
    """Fallback: create DB with hardcoded test airports if NASR download fails."""
    conn = sqlite3.connect(DB_PATH)
    create_db(conn)
    test_airports = [
        ('KBJC','Rocky Mountain Metro','Broomfield','CO',5673,6673,'D',39.9088,-105.1172,1,0),
        ('KGXY','Greeley-Weld County','Greeley','CO',4697,5697,'E',40.4375,-104.6330,1,0),
        ('KFNL','Northern Colorado Regional','Fort Collins','CO',5016,5016,'E',40.4518,-105.0111,1,0),
        ('KDEN','Denver Intl','Denver','CO',5431,6431,'B',39.8561,-104.6737,1,1),
        ('KCYS','Cheyenne Regional','Cheyenne','WY',6156,7156,'D',41.1557,-104.8118,1,0),
        ('KRKS','Rock Springs-Sweetwater','Rock Springs','WY',6764,7764,'E',41.5942,-109.0652,1,0),
        ('KIDA','Idaho Falls Regional','Idaho Falls','ID',4744,5744,'D',43.5146,-112.0707,1,1),
        ('KSUN','Friedman Memorial','Hailey','ID',5315,6315,'E',43.5044,-114.2957,1,0),
    ]
    test_runways = [
        ('KBJC','12R/30L',9000,100,'ASPH','HIRL','STD'),
        ('KBJC','12L/30R',7002,75,'ASPH','MED','STD'),
        ('KSUN','13/31',7550,100,'ASPH','HIRL','STD'),
        ('KDEN','16R/34L',16000,200,'CONC','HIRL','STD'),
        ('KDEN','16L/34R',12000,150,'CONC','HIRL','STD'),
        ('KFNL','15/33',8500,100,'ASPH','MIRL','STD'),
        ('KCYS','09/27',9200,150,'ASPH','HIRL','STD'),
        ('KIDA','02/20',9001,150,'ASPH','HIRL','STD'),
    ]
    test_freqs = [
        ('KBJC','ATIS','120.300'),
        ('KBJC','TWR','118.900'),
        ('KBJC','GND','121.700'),
        ('KSUN','CTAF','118.200'),
        ('KSUN','AWOS','135.725'),
        ('KDEN','ATIS','132.350'),
        ('KDEN','TWR','132.850'),
        ('KFNL','CTAF','119.400'),
        ('KCYS','TWR','124.100'),
        ('KIDA','TWR','118.500'),
    ]
    conn.executemany("INSERT OR REPLACE INTO airports VALUES (?,?,?,?,?,?,?,?,?,?,?)", test_airports)
    conn.executemany("INSERT INTO runways (icao,rwy_id,length_ft,width_ft,surface,lighting,pattern_dir) VALUES (?,?,?,?,?,?,?)", test_runways)
    conn.executemany("INSERT INTO frequencies (icao,freq_type,frequency) VALUES (?,?,?)", test_freqs)
    conn.execute("CREATE INDEX IF NOT EXISTS idx_airports_lat_lon ON airports(lat, lon)")
    conn.execute("CREATE INDEX IF NOT EXISTS idx_runways_icao ON runways(icao)")
    conn.execute("CREATE INDEX IF NOT EXISTS idx_frequencies_icao ON frequencies(icao)")
    conn.commit()
    conn.close()
    from datetime import date
    VERSION_FILE.write_text(date.today().isoformat())
    print(f"Created minimal test DB with {len(test_airports)} airports, {len(test_runways)} runways, {len(test_freqs)} frequencies")

if __name__ == "__main__":
    main()
