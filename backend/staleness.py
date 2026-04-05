from pathlib import Path
from datetime import date
import logging

VERSION_FILE = Path(__file__).parent.parent / "data" / "nasr_version.txt"

def check_staleness():
    try:
        version_date = date.fromisoformat(VERSION_FILE.read_text().strip())
        age = (date.today() - version_date).days
        if age > 30:
            logging.warning(f"NASR data is {age} days old -- consider running scripts/download_nasr.py")
        else:
            logging.info(f"NASR data is {age} days old (current)")
    except Exception as e:
        logging.warning(f"Could not check NASR staleness: {e}")
