import asyncio, httpx, time
from typing import Optional

_cache: dict = {}
CACHE_TTL = 300  # 5 minutes

async def get_metars(icao_list: list) -> dict:
    if not icao_list:
        return {}

    now = time.time()
    needed = []
    result = {}

    for icao in icao_list:
        key = icao.upper()
        if key in _cache and now - _cache[key]['ts'] < CACHE_TTL:
            result[key] = _cache[key]['data']
        else:
            needed.append(key)

    if needed:
        ids_str = ','.join(needed)
        url = f"https://aviationweather.gov/api/data/metar?ids={ids_str}&format=json&hours=2"
        try:
            async with httpx.AsyncClient(timeout=10) as client:
                resp = await client.get(url)
                resp.raise_for_status()
                data = resp.json()

                fetched = {}
                for item in data:
                    icao = item.get('icaoId', '').upper()
                    if not icao:
                        continue
                    fetched[icao] = {
                        'raw_metar': item.get('rawOb', 'N/A'),
                        'flight_category': item.get('fltcat', 'UNKNOWN').upper(),
                        'wind_dir': item.get('wdir'),
                        'wind_kt': item.get('wspd'),
                        'visibility_sm': item.get('visib'),
                        'ceiling_ft': item.get('ceil'),
                        'temp_c': item.get('temp'),
                        'altimeter_inhg': item.get('altim'),
                        'obs_time': item.get('obsTime'),
                    }

                for icao in needed:
                    if icao in fetched:
                        _cache[icao] = {'ts': now, 'data': fetched[icao]}
                        result[icao] = fetched[icao]
                    else:
                        fallback = {'flight_category': 'UNKNOWN', 'raw_metar': 'N/A',
                                    'wind_dir': None, 'wind_kt': None, 'visibility_sm': None,
                                    'ceiling_ft': None, 'temp_c': None, 'altimeter_inhg': None,
                                    'obs_time': None}
                        result[icao] = fallback
        except Exception as e:
            for icao in needed:
                result[icao] = {'flight_category': 'UNKNOWN', 'raw_metar': f'Error: {e}',
                                'wind_dir': None, 'wind_kt': None, 'visibility_sm': None,
                                'ceiling_ft': None, 'temp_c': None, 'altimeter_inhg': None,
                                'obs_time': None}

    return result
