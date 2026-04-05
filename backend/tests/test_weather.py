import asyncio, sys
from pathlib import Path
sys.path.insert(0, str(Path(__file__).parent.parent.parent))
from backend.weather import get_metars

def test_metar_fetch():
    result = asyncio.run(get_metars(["KBJC"]))
    assert "KBJC" in result
    assert "flight_category" in result["KBJC"]

def test_empty_list():
    result = asyncio.run(get_metars([]))
    assert result == {}
