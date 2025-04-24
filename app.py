
from flask import Flask, request, jsonify
from openai import OpenAI
from skyfield.api import load, wgs84
from datetime import datetime, timedelta
import os
import requests
import logging

app = Flask(__name__)
client = OpenAI(api_key=os.getenv("OPENAI_API_KEY"))

# Logging
logging.basicConfig(level=logging.INFO)

# Download ephemeris if not present
EPHEMERIS_PATH = "/tmp/de440s.bsp"
EPHEMERIS_URL = "https://naif.jpl.nasa.gov/pub/naif/generic_kernels/spk/planets/de440s.bsp"

if not os.path.exists(EPHEMERIS_PATH):
    import urllib.request
    logging.info("Downloading ephemeris...")
    urllib.request.urlretrieve(EPHEMERIS_URL, EPHEMERIS_PATH)
    logging.info("Ephemeris downloaded.")

# Planet key mappings to de440s supported barycenters
PLANET_KEYS = {
    "sun": "10",
    "moon": "301",
    "mercury": "1",
    "venus": "2",
    "earth": "399",
    "mars": "4",
    "jupiter": "5",
    "saturn": "6",
    "uranus": "7",
    "neptune": "8",
    "pluto": "9"
}

PLANET_NAMES = {
    "sun": "Güneş", "moon": "Ay", "mercury": "Merkür", "venus": "Venüs",
    "mars": "Mars", "jupiter": "Jüpiter", "saturn": "Satürn",
    "uranus": "Uranüs", "neptune": "Neptün", "pluto": "Plüton"
}

ZODIAC_SIGNS = [
    "Koç", "Boğa", "İkizler", "Yengeç", "Aslan", "Başak",
    "Terazi", "Akrep", "Yay", "Oğlak", "Kova", "Balık"
]

ASPECTS = {
    "Conjunction": 0,
    "Opposition": 180,
    "Square": 90,
    "Trine": 120,
    "Sextile": 60
}

ts = load.timescale()
eph = load(EPHEMERIS_PATH)

def get_zodiac_sign(degree):
    index = int(degree // 30) % 12
    return ZODIAC_SIGNS[index]

def angle_difference(a1, a2):
    diff = abs(a1 - a2) % 360
    return min(diff, 360 - diff)

def find_aspects(planets):
    aspects = []
    for i, p1 in enumerate(planets):
        for j, p2 in enumerate(planets):
            if i >= j:
                continue
            diff = angle_difference(p1["absolute_degree"], p2["absolute_degree"])
            for name, val in ASPECTS.items():
                if abs(diff - val) <= 6:
                    aspects.append({
                        "between": f"{p1['name']} & {p2['name']}",
                        "aspect": name,
                        "orb": round(abs(diff - val), 2)
                    })
    return aspects

@app.route("/natal-chart", methods=["POST"])
def natal_chart():
    try:
        data = request.json
        date = data.get("date")
        time_str = data.get("time")
        lat = float(data.get("lat"))
        lon = float(data.get("lon"))
        tz = data.get("tz", "+00:00")

        dt_local = datetime.fromisoformat(f"{date}T{time_str}")
        sign = 1 if tz[0] == "+" else -1
        hours = int(tz[1:3])
        minutes = int(tz[4:6]) if len(tz) > 3 else 0
        offset = sign * (hours + minutes / 60)
        dt_utc = dt_local - timedelta(hours=offset)

        t = ts.utc(dt_utc.year, dt_utc.month, dt_utc.day, dt_utc.hour, dt_utc.minute)
        observer = eph["399"].at(t)

        chart = []
        for key, spk_id in PLANET_KEYS.items():
            if key == "earth":
                continue
            body = eph[spk_id]
            astrometric = observer.observe(body).apparent()
            lon_deg = astrometric.ecliptic_latlon()[1].degrees

            retrograde = False
            t2 = ts.utc((dt_utc - timedelta(days=1)).year, (dt_utc - timedelta(days=1)).month, (dt_utc - timedelta(days=1)).day,
                        dt_utc.hour, dt_utc.minute)
            prev_lon = eph["399"].at(t2).observe(body).apparent().ecliptic_latlon()[1].degrees
            retrograde = (lon_deg - prev_lon) % 360 < 0

            chart.append({
                "name": PLANET_NAMES[key],
                "sign": get_zodiac_sign(lon_deg),
                "degree": round(lon_deg % 30, 2),
                "absolute_degree": round(lon_deg, 2),
                "retrograde": retrograde
            })

        return jsonify({
            "chart": chart,
            "aspects": find_aspects(chart),
            "date": date,
            "time": time_str,
            "timezone": tz
        })

    except Exception as e:
        return jsonify({"error": str(e)}), 400

@app.route("/health", methods=["GET"])
def health_check():
    return jsonify({"status": "ok"})

if __name__ == "__main__":
    from waitress import serve
    port = int(os.environ.get("PORT", 5000))
    serve(app, host="0.0.0.0", port=port)
