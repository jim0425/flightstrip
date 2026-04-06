# Run with: py scripts/migrate_ctaf.py
# Reads CTAF frequency from APT.txt (pos 988-995) for every airport
# that has zero frequency records in the DB — fixes all non-towered airports
import sqlite3, zipfile, re
from pathlib import Path

DB_PATH  = Path(__file__).parent.parent / "data" / "airports.db"
ZIP_PATH = Path(__file__).parent.parent / "data" / "nasr_raw" / "nasr.zip"

def main():
    conn = sqlite3.connect(DB_PATH)

    # Which airports already have at least one frequency row?
    has_freq = {r[0] for r in conn.execute("SELECT DISTINCT icao FROM frequencies")}
    print(f"Airports with existing freq data: {len(has_freq)}")

    inserted = 0
    skipped  = 0

    with zipfile.ZipFile(ZIP_PATH) as zf:
        apt_file = [n for n in zf.namelist() if 'APT' in n.upper() and n.endswith('.txt')][0]
        with zf.open(apt_file) as f:
            for raw in f:
                try:
                    line = raw.decode('latin-1')
                except Exception:
                    continue
                if not line.startswith('APT'):
                    continue
                if len(line) < 996:
                    continue
                try:
                    faa_lid = line[27:31].strip()
                    icao = line[1210:1217].strip() if len(line) > 1217 else ''
                    if not icao:
                        if len(faa_lid) == 3 and faa_lid.isalpha():
                            icao = 'K' + faa_lid
                        else:
                            icao = faa_lid
                    if not icao or icao in has_freq:
                        skipped += 1
                        continue

                    ctaf_raw = line[988:996].strip()
                    # Validate — must look like a VHF aviation frequency (108-137 MHz)
                    # 118.xxx (tower), 122.xxx (CTAF/UNICOM), 123.x, 124.x etc.
                    m = re.match(r'^(1[1-3]\d\.\d{1,3})', ctaf_raw)
                    if not m:
                        continue

                    freq = m.group(1)
                    conn.execute(
                        "INSERT INTO frequencies (icao, freq_type, frequency) VALUES (?, ?, ?)",
                        (icao, 'CTAF', freq)
                    )
                    has_freq.add(icao)
                    inserted += 1
                except Exception:
                    continue

    conn.commit()
    conn.close()

    print(f"Inserted {inserted} CTAF records for previously-empty airports")
    print(f"Skipped  {skipped} airports (already had frequency data)")

    # Quick verify
    conn2 = sqlite3.connect(DB_PATH)
    for icao in ['KBDU', 'KGXY', 'KLMO', 'KFNL']:
        rows = conn2.execute("SELECT freq_type, frequency FROM frequencies WHERE icao=?", (icao,)).fetchall()
        print(f"  {icao}: {rows}")
    conn2.close()

if __name__ == "__main__":
    main()
