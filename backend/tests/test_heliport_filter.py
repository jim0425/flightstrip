import sys
from pathlib import Path
sys.path.insert(0, str(Path(__file__).parent.parent.parent))
from backend.route import get_route_airports

def test_heliport_filter_default():
    airports = get_route_airports("KBJC", "KSUN", 25)
    site_types = [a.get('site_type', 'A') for a in airports]
    assert 'H' not in site_types, f"Found heliports in default response: {[a['icao'] for a in airports if a.get('site_type')=='H']}"

def test_heliport_filter_disabled():
    with_helis = get_route_airports("KBJC", "KSUN", 50, exclude_heliports=False, public_only=False)
    without_helis = get_route_airports("KBJC", "KSUN", 50, exclude_heliports=True, public_only=False)
    assert len(with_helis) >= len(without_helis)

def test_public_only_filter():
    public = get_route_airports("KBJC", "KSUN", 50, exclude_heliports=False, public_only=True)
    all_apts = get_route_airports("KBJC", "KSUN", 50, exclude_heliports=False, public_only=False)
    assert len(all_apts) >= len(public)

def test_default_returns_reasonable_count():
    airports = get_route_airports("KBJC", "KSUN", 25)
    print(f"Default filter: {len(airports)} airports")
    assert len(airports) <= 40, f"Too many airports: {len(airports)} (expected <= 40 after filtering)"
    assert len(airports) >= 2
