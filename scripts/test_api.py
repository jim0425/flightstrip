# Run with: py scripts/test_api.py
import urllib.request, json, sys, io
sys.stdout = io.TextIOWrapper(sys.stdout.buffer, encoding='utf-8', errors='replace')

BASE = "http://localhost:8000"

def post(path, body):
    data = json.dumps(body).encode()
    req = urllib.request.Request(
        BASE + path, data=data,
        headers={"Content-Type": "application/json"}, method="POST"
    )
    try:
        resp = urllib.request.urlopen(req, timeout=30)
        return resp.status, json.loads(resp.read())
    except urllib.error.HTTPError as e:
        return e.code, json.loads(e.read())

def get(path):
    try:
        resp = urllib.request.urlopen(BASE + path, timeout=10)
        return resp.status, json.loads(resp.read())
    except urllib.error.HTTPError as e:
        return e.code, json.loads(e.read())

print("=" * 60)
print("TEST 1: /health")
s, b = get("/health")
print(f"  Status: {s}  body: {b}")
assert s == 200, "FAIL: health check"
print("  PASS")

print()
print("TEST 2: /route 2-waypoint (KBJC -> KSUN)")
s, b = post("/route", {"waypoints": ["KBJC","KSUN"], "corridor_nm": 25, "mode": "vfr",
                        "exclude_heliports": True, "public_only": True, "min_runway_ft": 0})
print(f"  Status: {s}")
if s != 200:
    print(f"  ERROR body: {json.dumps(b, indent=2)[:500]}")
    sys.exit(1)
print(f"  airports: {len(b['route'])}  label: {b.get('route_label')}  dist: {b['summary']['distance_nm']}nm")
print("  PASS")

print()
print("TEST 3: /route 3-waypoint (KBJC -> KGXY -> KPUB) — the failing case")
s, b = post("/route", {"waypoints": ["KBJC","KGXY","KPUB"], "corridor_nm": 25, "mode": "vfr",
                        "exclude_heliports": True, "public_only": True, "min_runway_ft": 0})
print(f"  Status: {s}")
if s != 200:
    print(f"  ERROR body: {json.dumps(b, indent=2)}")
    sys.exit(1)
icaos = [a["icao"] for a in b["route"]]
print(f"  airports: {len(b['route'])}  label: {b.get('route_label')}")
print(f"  ICAOs: {icaos}")
print("  PASS")

print()
print("TEST 4: /route 4-waypoint")
s, b = post("/route", {"waypoints": ["KBJC","KFNL","KCYS","KRKS"], "corridor_nm": 25, "mode": "vfr",
                        "exclude_heliports": True, "public_only": True, "min_runway_ft": 0})
print(f"  Status: {s}")
if s != 200:
    print(f"  ERROR body: {json.dumps(b, indent=2)[:500]}")
else:
    print(f"  airports: {len(b['route'])}  label: {b.get('route_label')}")
    print("  PASS")

print()
print("TEST 5: Legacy from/to still works")
s, b = post("/route", {"from": "KBJC", "to": "KSUN", "corridor_nm": 25, "mode": "vfr"})
print(f"  Status: {s}")
if s != 200:
    print(f"  ERROR body: {json.dumps(b, indent=2)[:500]}")
else:
    print(f"  airports: {len(b['route'])}  label: {b.get('route_label')}")
    print("  PASS")

print()
print("TEST 6: computed fields present (pattern_display, freq_ctaf_tower, is_towered)")
s, b = post("/route", {"waypoints": ["KBJC","KSUN"], "corridor_nm": 25, "mode": "vfr",
                        "exclude_heliports": True, "public_only": True, "min_runway_ft": 0})
if s == 200 and b["route"]:
    apt = b["route"][0]
    fields = ["pattern_display","freq_ctaf_tower","freq_atis","is_towered","name_abbrev","city_abbrev","has_ils"]
    missing = [f for f in fields if f not in apt]
    if missing:
        print(f"  FAIL — missing fields: {missing}")
    else:
        print(f"  PASS — all computed fields present")
        print(f"  KBJC pattern_display: {apt['pattern_display']}")
        print(f"  KBJC freq_ctaf_tower: {apt['freq_ctaf_tower']}  is_towered: {apt['is_towered']}")
        print(f"  KBJC name_abbrev: '{apt['name_abbrev']}'  city_abbrev: '{apt['city_abbrev']}'")

print()
print("TEST 7: /route/pdf POST returns content")
data = json.dumps({"waypoints": ["KBJC","KSUN"], "corridor_nm": 25, "mode": "vfr",
                   "exclude_heliports": True, "public_only": True, "min_runway_ft": 0}).encode()
req7 = urllib.request.Request("http://localhost:8000/route/pdf", data=data,
                               headers={"Content-Type": "application/json"}, method="POST")
try:
    resp7 = urllib.request.urlopen(req7, timeout=30)
    ct = resp7.headers.get("Content-Type", "")
    body7 = resp7.read()
    print(f"  Status: 200  Content-Type: {ct}  Size: {len(body7)} bytes")
    assert len(body7) > 500, "Response too small"
    print("  PASS")
except urllib.error.HTTPError as e:
    print(f"  FAIL: {e.code} {e.read()[:200]}")

print()
print("ALL TESTS COMPLETE")
