# Run with: python scripts/check_nasr_staleness.py
from pathlib import Path
from datetime import date

VERSION_FILE = Path(__file__).parent.parent / "data" / "nasr_version.txt"

def main():
    try:
        version_date = date.fromisoformat(VERSION_FILE.read_text().strip())
        age = (date.today() - version_date).days
        if age > 30:
            print(f"WARNING: NASR data is {age} days old. Run: python scripts/download_nasr.py")
        else:
            print(f"OK: NASR data is {age} days old (last updated: {version_date})")
    except FileNotFoundError:
        print("WARNING: data/nasr_version.txt not found. Run: python scripts/download_nasr.py")
    except Exception as e:
        print(f"ERROR: {e}")

if __name__ == "__main__":
    main()
