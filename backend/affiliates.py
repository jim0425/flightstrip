# Run with: python -c "from backend.affiliates import get_affiliates; print(get_affiliates({'icao':'KBJC','elevation_ft':5673,'frequencies':[{'freq_type':'TWR','frequency':'118.9'}]}, 'vfr'))"

def get_affiliates(airport: dict, mode: str) -> list:
    """Return contextual affiliate links for an airport card."""
    links = []
    elevation = airport.get('elevation_ft', 0) or 0
    freqs = airport.get('frequencies', [])
    has_tower = any(f.get('freq_type', '').upper() == 'TWR' for f in freqs)

    # Mountain/high-elevation airports
    if elevation > 5000:
        links.append({
            "label": "Mountain Flying Course",
            "url": "https://www.sportys.com/PLACEHOLDER-MOUNTAIN-FLYING",
            "reason": "high elevation airport"
        })

    # Tower airports -> premium headset
    if has_tower:
        links.append({
            "label": "Bose A20 Headset",
            "url": "https://amzn.to/PLACEHOLDER-BOSE-A20",
            "reason": "tower airport"
        })

    # Student mode
    if mode == "student":
        links.append({
            "label": "King Schools Ground School",
            "url": "https://www.kingschools.com/PLACEHOLDER-GROUND-SCHOOL",
            "reason": "student mode"
        })
        links.append({
            "label": "Gleim Written Test Prep",
            "url": "https://www.gleim.com/aviation/PLACEHOLDER",
            "reason": "student mode"
        })

    # IFR mode
    if mode == "ifr":
        links.append({
            "label": "ForeFlight Subscription",
            "url": "https://foreflight.com/PLACEHOLDER-AFFILIATE",
            "reason": "ifr mode"
        })

    return links[:3]  # max 3 per card
