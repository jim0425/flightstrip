import pytest, sys
from pathlib import Path
sys.path.insert(0, str(Path(__file__).parent.parent.parent))
from backend.route import get_route_airports

def test_route_kbjc_ksun():
    airports = get_route_airports("KBJC", "KSUN", 25)
    assert len(airports) >= 2
    icaos = [a['icao'] for a in airports]
    assert "KBJC" in icaos
    assert "KSUN" in icaos

def test_corridor_filter():
    narrow = get_route_airports("KBJC", "KSUN", 10)
    wide = get_route_airports("KBJC", "KSUN", 50)
    assert len(wide) >= len(narrow)

def test_airports_sorted_by_along_track():
    airports = get_route_airports("KBJC", "KSUN", 25)
    along_values = [a['along_track_nm'] for a in airports]
    assert along_values == sorted(along_values)

def test_invalid_airport_raises():
    with pytest.raises(ValueError):
        get_route_airports("XXXX", "KSUN", 25)
