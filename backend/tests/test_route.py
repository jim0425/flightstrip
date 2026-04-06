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

def test_multi_waypoint():
    from backend.route import get_multi_waypoint_airports
    airports = get_multi_waypoint_airports(["KBJC", "KSUN"], 25)
    assert len(airports) >= 2

def test_multi_waypoint_three_stops():
    from backend.route import get_multi_waypoint_airports
    airports = get_multi_waypoint_airports(["KBJC", "KSUN", "KGXY"], 25)
    icaos = [a['icao'] for a in airports]
    assert "KBJC" in icaos
    assert len(airports) >= 3

def test_computed_fields():
    from backend.route import get_route_airports
    r = get_route_airports("KBJC", "KSUN", 25)
    assert len(r) >= 2
    apt = r[0]
    assert 'pattern_display' in apt
    assert 'name_abbrev' in apt
    assert 'city_abbrev' in apt
    assert 'freq_ctaf_tower' in apt
    assert 'is_towered' in apt
    assert 'has_ils' in apt
