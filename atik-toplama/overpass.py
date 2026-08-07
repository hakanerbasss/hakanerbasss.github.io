"""Bir mahalle adından OSM sokak (yol) verisini çeken yardımcı modül.

Akış:
  1. Nominatim ile mahalle adını bir OSM 'relation' sınırına çözümle.
  2. Overpass API ile o sınır içindeki isimli yolları (highway=*) geometrileriyle çek.

Not: Nominatim ve Overpass halka açık, ücretsiz servislerdir; kullanım
politikaları gereği istekler arası makul aralık ve User-Agent zorunludur.
"""
import time
import requests

NOMINATIM_URL = 'https://nominatim.openstreetmap.org/search'
OVERPASS_URL = 'https://overpass-api.de/api/interpreter'
USER_AGENT = 'kaba-atik-rota-app/1.0 (belediye ic kullanim)'

HIGHWAY_TYPES = [
    'residential', 'tertiary', 'secondary', 'primary', 'unclassified',
    'living_street', 'service', 'pedestrian',
]


class NeighborhoodNotFound(Exception):
    pass


def _overpass_post(query, retries=2, request_timeout=60):
    """Overpass'a sorgu gönderir; genel (ücretsiz) sunucu yoğunlukta sık sık
    429/502/503/504 döner — bu gerçek bir "veri yok" durumu değildir, bu
    yüzden birkaç kez artan bekleme ile yeniden denenir."""
    last_error = None
    for attempt in range(retries):
        try:
            resp = requests.post(
                OVERPASS_URL,
                data={'data': query},
                headers={'User-Agent': USER_AGENT},
                timeout=request_timeout,
            )
            if resp.status_code in (429, 502, 503, 504):
                last_error = Exception(f'Overpass geçici hata döndü: HTTP {resp.status_code}')
                time.sleep(5 * (attempt + 1))
                continue
            resp.raise_for_status()
            return resp.json()
        except requests.RequestException as e:
            last_error = e
            time.sleep(5 * (attempt + 1))
    raise last_error or Exception('Overpass sorgusu başarısız oldu')


def resolve_neighborhood(query):
    """Mahalle adını Nominatim ile OSM relation'a çözer.

    query: örn. "Gümüşpala Mahallesi, Avcılar, İstanbul"
    Döner: {'osm_id': int, 'display_name': str, 'lat': float, 'lon': float}
    """
    resp = requests.get(
        NOMINATIM_URL,
        params={
            'q': query,
            'format': 'json',
            'limit': 5,
            'countrycodes': 'tr',
            'addressdetails': 1,
        },
        headers={'User-Agent': USER_AGENT},
        timeout=20,
    )
    resp.raise_for_status()
    results = resp.json()
    for r in results:
        if r.get('osm_type') == 'relation':
            return {
                'osm_id': int(r['osm_id']),
                'display_name': r['display_name'],
                'lat': float(r['lat']),
                'lon': float(r['lon']),
            }
    if results:
        r = results[0]
        return {
            'osm_id': int(r['osm_id']) if r.get('osm_type') == 'relation' else None,
            'display_name': r['display_name'],
            'lat': float(r['lat']),
            'lon': float(r['lon']),
        }
    raise NeighborhoodNotFound(f"'{query}' için mahalle sınırı bulunamadı")


def search_districts(province_name):
    """İl adından ilçe listesini Overpass ile döner."""
    resp = requests.get(
        NOMINATIM_URL,
        params={'q': f'{province_name}, Türkiye', 'format': 'json', 'limit': 5,
                'countrycodes': 'tr', 'featuretype': 'state'},
        headers={'User-Agent': USER_AGENT},
        timeout=20,
    )
    resp.raise_for_status()
    results = resp.json()
    osm_id = None
    for r in results:
        if r.get('osm_type') == 'relation':
            osm_id = int(r['osm_id'])
            break
    if not osm_id:
        # featuretype=state bazen çalışmaz; tekrar dene
        resp2 = requests.get(
            NOMINATIM_URL,
            params={'q': f'{province_name}, Türkiye', 'format': 'json', 'limit': 10,
                    'countrycodes': 'tr'},
            headers={'User-Agent': USER_AGENT},
            timeout=20,
        )
        resp2.raise_for_status()
        for r in resp2.json():
            if r.get('osm_type') == 'relation':
                osm_id = int(r['osm_id'])
                break
    if not osm_id:
        raise NeighborhoodNotFound(f"'{province_name}' ili OSM'de bulunamadı")

    area_id = 3600000000 + osm_id
    query = f"""
    [out:json][timeout:60];
    area({area_id})->.p;
    relation(area.p)["admin_level"="6"]["name"]["boundary"="administrative"];
    out tags;
    """
    data = _overpass_post(query)
    districts = []
    for el in data.get('elements', []):
        name = el.get('tags', {}).get('name')
        if name:
            districts.append({'name': name, 'osm_id': el.get('id')})
    districts.sort(key=lambda x: x['name'])
    return districts


def search_neighborhoods(district_name, province_name):
    """İlçe adından mahalle listesini Overpass ile döner."""
    resp = requests.get(
        NOMINATIM_URL,
        params={'q': f'{district_name}, {province_name}, Türkiye',
                'format': 'json', 'limit': 5, 'countrycodes': 'tr'},
        headers={'User-Agent': USER_AGENT},
        timeout=20,
    )
    resp.raise_for_status()
    results = resp.json()
    osm_id = None
    for r in results:
        if r.get('osm_type') == 'relation':
            osm_id = int(r['osm_id'])
            break
    if not osm_id:
        raise NeighborhoodNotFound(f"'{district_name}' ilçesi OSM'de bulunamadı")

    area_id = 3600000000 + osm_id
    query = f"""
    [out:json][timeout:60];
    area({area_id})->.d;
    relation(area.d)["admin_level"~"^(8|9|10)$"]["name"]["boundary"="administrative"];
    out tags;
    """
    data = _overpass_post(query)
    neighborhoods = []
    for el in data.get('elements', []):
        name = el.get('tags', {}).get('name')
        if name:
            neighborhoods.append({'name': name, 'osm_id': el.get('id')})
    neighborhoods.sort(key=lambda x: x['name'])
    return neighborhoods


def fetch_streets(osm_relation_id):
    """Verilen relation id sınırı içindeki isimli yolları geometrileriyle döner.

    Döner: [{'osm_way_id': int, 'name': str, 'coords': [[lat, lon], ...]}, ...]
    """
    highway_filter = '|'.join(HIGHWAY_TYPES)
    area_id = 3600000000 + osm_relation_id  # Overpass area id konvansiyonu
    query = f"""
    [out:json][timeout:90];
    area({area_id})->.a;
    way(area.a)["highway"~"^({highway_filter})$"]["name"];
    out geom;
    """
    data = _overpass_post(query, request_timeout=90)

    streets = {}
    for el in data.get('elements', []):
        if el.get('type') != 'way':
            continue
        name = el.get('tags', {}).get('name')
        if not name or 'geometry' not in el:
            continue
        coords = [[pt['lat'], pt['lon']] for pt in el['geometry']]
        key = name.strip().lower()
        # Aynı isimli parçalı yol segmentlerini tek sokak kaydı altında birleştir
        if key not in streets:
            streets[key] = {'osm_way_id': el['id'], 'name': name.strip(), 'coords': coords}
        else:
            streets[key]['coords'].extend(coords)
    return list(streets.values())
