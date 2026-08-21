"""Offline airport catalog used when Duffel is not configured.

The TypeScript template always calls ``duffel.suggestions.list``. Python keeps
the same result shape, and this catalog stands in for that API in Studio/mock
mode so queries like ``Delhi`` / ``DEL`` resolve instead of falling back to
JFK/LAX/LHR/SFO.
"""

from __future__ import annotations

from typing import Any, Dict, List, Optional


def _arp(
    iata: str,
    icao: str,
    name: str,
    city: str,
    country: str,
    lat: float,
    lon: float,
    tz: str,
    *keywords: str,
) -> Dict[str, Any]:
    return {
        "id": f"arp_{iata.lower()}_{country.lower()}",
        "name": name,
        "iata_code": iata,
        "icao_code": icao,
        "city_name": city,
        "type": "airport",
        "latitude": lat,
        "longitude": lon,
        "time_zone": tz,
        "keywords": list(keywords),
    }


MOCK_AIRPORTS: List[Dict[str, Any]] = [
    _arp("DEL", "VIDP", "Indira Gandhi International Airport", "Delhi", "in", 28.5562, 77.1000, "Asia/Kolkata", "new delhi", "delhi ncr", "indira gandhi"),
    _arp("BOM", "VABB", "Chhatrapati Shivaji Maharaj International Airport", "Mumbai", "in", 19.0896, 72.8656, "Asia/Kolkata", "bombay"),
    _arp("BLR", "VOBL", "Kempegowda International Airport", "Bengaluru", "in", 13.1986, 77.7066, "Asia/Kolkata", "bangalore"),
    _arp("MAA", "VOMM", "Chennai International Airport", "Chennai", "in", 12.9941, 80.1709, "Asia/Kolkata", "madras"),
    _arp("HYD", "VOHS", "Rajiv Gandhi International Airport", "Hyderabad", "in", 17.2403, 78.4294, "Asia/Kolkata"),
    _arp("CCU", "VECC", "Netaji Subhas Chandra Bose International Airport", "Kolkata", "in", 22.6547, 88.4467, "Asia/Kolkata", "calcutta"),
    _arp("AMD", "VAAH", "Sardar Vallabhbhai Patel International Airport", "Ahmedabad", "in", 23.0772, 72.6347, "Asia/Kolkata"),
    _arp("GOI", "VOGO", "Manohar International Airport", "Goa", "in", 15.3808, 73.8314, "Asia/Kolkata", "dabolim", "mopa"),
    _arp("LHR", "EGLL", "London Heathrow Airport", "London", "gb", 51.4700, -0.4543, "Europe/London", "heathrow"),
    _arp("LGW", "EGKK", "London Gatwick Airport", "London", "gb", 51.1537, -0.1821, "Europe/London", "gatwick"),
    _arp("STN", "EGSS", "London Stansted Airport", "London", "gb", 51.8860, 0.2389, "Europe/London", "stansted"),
    _arp("LCY", "EGLC", "London City Airport", "London", "gb", 51.5053, 0.0553, "Europe/London"),
    _arp("MAN", "EGCC", "Manchester Airport", "Manchester", "gb", 53.3537, -2.2750, "Europe/London"),
    _arp("EDI", "EGPH", "Edinburgh Airport", "Edinburgh", "gb", 55.9500, -3.3725, "Europe/London"),
    _arp("JFK", "KJFK", "John F. Kennedy International Airport", "New York", "us", 40.6413, -73.7781, "America/New_York", "nyc", "new york city"),
    _arp("EWR", "KEWR", "Newark Liberty International Airport", "Newark", "us", 40.6895, -74.1745, "America/New_York", "new york", "nyc"),
    _arp("LGA", "KLGA", "LaGuardia Airport", "New York", "us", 40.7769, -73.8740, "America/New_York", "nyc"),
    _arp("LAX", "KLAX", "Los Angeles International Airport", "Los Angeles", "us", 33.9416, -118.4085, "America/Los_Angeles"),
    _arp("SFO", "KSFO", "San Francisco International Airport", "San Francisco", "us", 37.6213, -122.3790, "America/Los_Angeles"),
    _arp("ORD", "KORD", "O'Hare International Airport", "Chicago", "us", 41.9742, -87.9073, "America/Chicago"),
    _arp("ATL", "KATL", "Hartsfield-Jackson Atlanta International Airport", "Atlanta", "us", 33.6407, -84.4277, "America/New_York"),
    _arp("MIA", "KMIA", "Miami International Airport", "Miami", "us", 25.7959, -80.2870, "America/New_York"),
    _arp("SEA", "KSEA", "Seattle-Tacoma International Airport", "Seattle", "us", 47.4502, -122.3088, "America/Los_Angeles"),
    _arp("BOS", "KBOS", "Boston Logan International Airport", "Boston", "us", 42.3656, -71.0096, "America/New_York"),
    _arp("IAD", "KIAD", "Washington Dulles International Airport", "Washington", "us", 38.9531, -77.4565, "America/New_York", "dc", "dulles"),
    _arp("DFW", "KDFW", "Dallas/Fort Worth International Airport", "Dallas", "us", 32.8998, -97.0403, "America/Chicago"),
    _arp("CDG", "LFPG", "Charles de Gaulle Airport", "Paris", "fr", 49.0097, 2.5479, "Europe/Paris"),
    _arp("AMS", "EHAM", "Amsterdam Airport Schiphol", "Amsterdam", "nl", 52.3105, 4.7683, "Europe/Amsterdam"),
    _arp("FRA", "EDDF", "Frankfurt Airport", "Frankfurt", "de", 50.0379, 8.5622, "Europe/Berlin"),
    _arp("MUC", "EDDM", "Munich Airport", "Munich", "de", 48.3537, 11.7750, "Europe/Berlin"),
    _arp("MAD", "LEMD", "Adolfo Suárez Madrid–Barajas Airport", "Madrid", "es", 40.4983, -3.5676, "Europe/Madrid"),
    _arp("BCN", "LEBL", "Josep Tarradellas Barcelona–El Prat Airport", "Barcelona", "es", 41.2974, 2.0833, "Europe/Madrid"),
    _arp("FCO", "LIRF", "Leonardo da Vinci–Fiumicino Airport", "Rome", "it", 41.8003, 12.2389, "Europe/Rome"),
    _arp("ZRH", "LSZH", "Zurich Airport", "Zurich", "ch", 47.4647, 8.5492, "Europe/Zurich"),
    _arp("DUB", "EIDW", "Dublin Airport", "Dublin", "ie", 53.4264, -6.2499, "Europe/Dublin"),
    _arp("DXB", "OMDB", "Dubai International Airport", "Dubai", "ae", 25.2532, 55.3657, "Asia/Dubai"),
    _arp("AUH", "OMAA", "Zayed International Airport", "Abu Dhabi", "ae", 24.4330, 54.6511, "Asia/Dubai"),
    _arp("DOH", "OTHH", "Hamad International Airport", "Doha", "qa", 25.2731, 51.6081, "Asia/Qatar"),
    _arp("IST", "LTFM", "Istanbul Airport", "Istanbul", "tr", 41.2753, 28.7519, "Europe/Istanbul"),
    _arp("HND", "RJTT", "Tokyo Haneda Airport", "Tokyo", "jp", 35.5494, 139.7798, "Asia/Tokyo", "haneda"),
    _arp("NRT", "RJAA", "Narita International Airport", "Tokyo", "jp", 35.7720, 140.3929, "Asia/Tokyo", "narita"),
    _arp("ICN", "RKSI", "Incheon International Airport", "Seoul", "kr", 37.4602, 126.4407, "Asia/Seoul"),
    _arp("SIN", "WSSS", "Singapore Changi Airport", "Singapore", "sg", 1.3644, 103.9915, "Asia/Singapore", "changi"),
    _arp("HKG", "VHHH", "Hong Kong International Airport", "Hong Kong", "hk", 22.3080, 113.9185, "Asia/Hong_Kong"),
    _arp("BKK", "VTBS", "Suvarnabhumi Airport", "Bangkok", "th", 13.6900, 100.7501, "Asia/Bangkok"),
    _arp("KUL", "WMKK", "Kuala Lumpur International Airport", "Kuala Lumpur", "my", 2.7456, 101.7099, "Asia/Kuala_Lumpur"),
    _arp("PEK", "ZBAA", "Beijing Capital International Airport", "Beijing", "cn", 40.0799, 116.6031, "Asia/Shanghai"),
    _arp("PVG", "ZSPD", "Shanghai Pudong International Airport", "Shanghai", "cn", 31.1443, 121.8083, "Asia/Shanghai"),
    _arp("SYD", "YSSY", "Sydney Kingsford Smith Airport", "Sydney", "au", -33.9399, 151.1753, "Australia/Sydney"),
    _arp("MEL", "YMML", "Melbourne Airport", "Melbourne", "au", -37.6690, 144.8410, "Australia/Melbourne"),
    _arp("YYZ", "CYYZ", "Toronto Pearson International Airport", "Toronto", "ca", 43.6777, -79.6248, "America/Toronto"),
    _arp("MEX", "MMMX", "Mexico City International Airport", "Mexico City", "mx", 19.4363, -99.0721, "America/Mexico_City"),
    _arp("GRU", "SBGR", "São Paulo/Guarulhos International Airport", "São Paulo", "br", -23.4356, -46.4731, "America/Sao_Paulo"),
]


def lookup_airport(code: str) -> Optional[Dict[str, Any]]:
    iata = (code or "").strip().upper()
    if not iata:
        return None
    for airport in MOCK_AIRPORTS:
        if airport["iata_code"] == iata:
            return dict(airport)
    return None


def _haystack(airport: Dict[str, Any]) -> str:
    parts = [
        airport.get("iata_code", ""),
        airport.get("icao_code", ""),
        airport.get("name", ""),
        airport.get("city_name", ""),
        *airport.get("keywords", []),
    ]
    return " ".join(str(p) for p in parts if p).lower()


def search_mock_airports(query: str, limit: int = 10) -> List[Dict[str, Any]]:
    """Ranked substring search. Empty / unmatched queries return [] (TS parity)."""
    q = (query or "").strip().lower()
    if len(q) < 2:
        return []

    scored: List[tuple[int, Dict[str, Any]]] = []
    for airport in MOCK_AIRPORTS:
        iata = str(airport.get("iata_code", "")).lower()
        icao = str(airport.get("icao_code", "")).lower()
        city = str(airport.get("city_name", "")).lower()
        name = str(airport.get("name", "")).lower()
        keywords = [str(k).lower() for k in airport.get("keywords", [])]
        if q == iata:
            score = 0
        elif q == city or q in keywords:
            score = 1
        elif iata.startswith(q) or icao.startswith(q):
            score = 2
        elif city.startswith(q):
            score = 3
        elif q in _haystack(airport) or any(q in k for k in (name, city, *keywords)):
            score = 4
        else:
            continue
        scored.append((score, airport))

    scored.sort(key=lambda item: (item[0], item[1]["iata_code"]))
    return [dict(item[1]) for item in scored[:limit]]
