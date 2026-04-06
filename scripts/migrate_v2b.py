# Run with: python scripts/migrate_v2b.py
import sqlite3, zipfile
from pathlib import Path

DB_PATH = Path(__file__).parent.parent / "data" / "airports.db"
ZIP_PATH = Path(__file__).parent.parent / "data" / "nasr_raw" / "nasr.zip"

def migrate():
    conn = sqlite3.connect(DB_PATH)

    # Add columns if missing
    existing = [row[1] for row in conn.execute("PRAGMA table_info(airports)")]
    if 'apt_type' not in existing:
        conn.execute("ALTER TABLE airports ADD COLUMN apt_type TEXT DEFAULT 'PU'")
        print("Added apt_type column")
    if 'site_type' not in existing:
        conn.execute("ALTER TABLE airports ADD COLUMN site_type TEXT DEFAULT 'A'")
        print("Added site_type column")
    conn.commit()

    if not ZIP_PATH.exists():
        print(f"NASR zip not found at {ZIP_PATH} — columns added with defaults only")
        return

    # Re-parse apt_type and site_type from NASR
    updated = 0
    counts = {}

    with zipfile.ZipFile(ZIP_PATH) as zf:
        with zf.open('APT.txt') as f:
            for raw_line in f:
                try:
                    line = raw_line.decode('latin-1')
                except:
                    continue
                if not line.startswith('APT'):
                    continue
                if len(line) < 600:
                    continue
                try:
                    # CONFIRMED POSITIONS from NASR probe:
                    # site_type: [14:15] — A(airport), H(heliport), S(seaplane), U(ultralight), G(gliderport), B(balloonport)
                    # apt_type (facility use): [183:185] — PU(public), PR(private), MA(military-AF), MR(military-restricted), MN(military-navy), CG(coast guard)
                    faa_lid = line[27:31].strip()
                    site_type = line[14:15].strip() or 'A'
                    apt_type = line[183:185].strip() or 'PU'

                    # Build icao same way as download_nasr.py
                    icao = line[1210:1217].strip() if len(line) > 1217 else ''
                    if not icao:
                        if len(faa_lid) == 3 and faa_lid.isalpha():
                            icao = 'K' + faa_lid
                        else:
                            icao = faa_lid

                    if icao:
                        conn.execute(
                            "UPDATE airports SET apt_type=?, site_type=? WHERE icao=?",
                            (apt_type, site_type, icao)
                        )
                        updated += 1
                        counts[site_type] = counts.get(site_type, 0) + 1
                except (ValueError, IndexError):
                    continue

    conn.commit()
    conn.close()

    print(f"Updated {updated} airport records")
    print(f"Site type breakdown: {dict(sorted(counts.items()))}")
    heliports = counts.get('H', 0)
    print(f"Heliports (H): {heliports}")

    # Verify
    conn2 = sqlite3.connect(DB_PATH)
    total = conn2.execute("SELECT COUNT(*) FROM airports").fetchone()[0]
    h_count = conn2.execute("SELECT COUNT(*) FROM airports WHERE site_type='H'").fetchone()[0]
    pu_count = conn2.execute("SELECT COUNT(*) FROM airports WHERE apt_type='PU'").fetchone()[0]
    kbjc = conn2.execute("SELECT icao, apt_type, site_type FROM airports WHERE icao='KBJC'").fetchone()
    conn2.close()
    print(f"Total airports: {total}, Heliports: {h_count}, Public (PU): {pu_count}")
    print(f"KBJC: {kbjc}")

if __name__ == "__main__":
    migrate()
