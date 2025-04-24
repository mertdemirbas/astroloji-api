
from flask import Flask, request, jsonify
from openai import OpenAI
from skyfield.api import load, Topos
from datetime import datetime, timedelta
import os
import requests
import logging

app = Flask(__name__)
client = OpenAI(api_key=os.getenv("OPENAI_API_KEY"))

# Logging
logging.basicConfig(level=logging.INFO, format="%(asctime)s - %(levelname)s - %(message)s")

# Ephemeris file download
EPHEMERIS_FILE = "de440s.bsp"
if not os.path.exists(EPHEMERIS_FILE):
    import urllib.request
    logging.info("Downloading ephemeris file...")
    url = "https://naif.jpl.nasa.gov/pub/naif/generic_kernels/spk/planets/de440s.bsp"
    urllib.request.urlretrieve(url, EPHEMERIS_FILE)
    logging.info("Ephemeris file downloaded.")

# Skyfield setup
ts = load.timescale()
eph = load(EPHEMERIS_FILE)

ZODIAC_SIGNS = [
    "Koç", "Boğa", "İkizler", "Yengeç", "Aslan", "Başak",
    "Terazi", "Akrep", "Yay", "Oğlak", "Kova", "Balık"
]
PLANET_KEYS = {
    "sun": "Güneş", "moon": "Ay", "mercury": "Merkür", "venus": "Venüs",
    "mars": "Mars", "jupiter": "Jüpiter", "saturn": "Satürn",
    "uranus": "Uranüs", "neptune": "Neptün", "pluto": "Plüton"
}
ASPECTS = {
    "Conjunction": 0, "Opposition": 180,
    "Square": 90, "Trine": 120, "Sextile": 60
}

def get_zodiac(degree):
    return ZODIAC_SIGNS[int(degree // 30) % 12]

def get_house(degree):
    return int(degree // 30) + 1

def angle_diff(a, b):
    diff = abs(a - b) % 360
    return diff if diff <= 180 else 360 - diff

def find_aspects(planets):
    results = []
    tolerance = 6
    for i, p1 in enumerate(planets):
        for j, p2 in enumerate(planets):
            if i >= j:
                continue
            diff = angle_diff(p1["absolute_degree"], p2["absolute_degree"])
            for aspect, angle in ASPECTS.items():
                if abs(diff - angle) <= tolerance:
                    results.append({
                        "between": f"{p1['name']} & {p2['name']}",
                        "aspect": aspect,
                        "orb": round(abs(diff - angle), 2)
                    })
    return results

@app.route("/natal-chart", methods=["POST"])
def natal_chart():
    try:
        data = request.json
        date = data["date"]
        time = data["time"]
        lat = float(data["lat"])
        lon = float(data["lon"])
        tz = data.get("tz", "+00:00")
        offset = int(tz.replace(":", "").replace("+", "")) // 100
        dt = datetime.fromisoformat(f"{date}T{time}") - timedelta(hours=offset)
        t = ts.utc(dt.year, dt.month, dt.day, dt.hour, dt.minute)

        chart = []
        earth = eph["earth"]
        for key in PLANET_KEYS:
            body = eph[key]
            pos = earth.at(t).observe(body).apparent()
            lon_deg = pos.ecliptic_latlon()[1].degrees
            t2 = ts.utc((dt - timedelta(days=2)).year, (dt - timedelta(days=2)).month,
                        (dt - timedelta(days=2)).day, dt.hour, dt.minute)
            lon2 = earth.at(t2).observe(body).apparent().ecliptic_latlon()[1].degrees
            retrograde = (lon_deg - lon2) % 360 > 180
            chart.append({
                "name": PLANET_KEYS[key],
                "sign": get_zodiac(lon_deg),
                "degree": round(lon_deg % 30, 2),
                "absolute_degree": round(lon_deg, 2),
                "retrograde": str(retrograde).lower(),
                "house": get_house(lon_deg)
            })

        return jsonify({
            "chart": chart,
            "aspects": find_aspects(chart),
            "date": date,
            "time": time,
            "timezone": tz,
            "location": {"lat": lat, "lon": lon}
        })
    except Exception as e:
        logging.error(str(e))
        return jsonify({"error": str(e)}), 400

# Horoscope translation endpoint
def fetch_from_horoscope_app(sign):
    try:
        url = f"https://horoscope-app-api.vercel.app/api/v1/get-horoscope/daily?sign={sign.lower()}&day=today"
        r = requests.get(url, timeout=5)
        if r.status_code == 200:
            return r.json()["data"]["horoscope_data"], "en"
    except:
        return None, None
    return None, None

def fetch_from_aztro(sign):
    try:
        url = f"https://aztro.sameerkumar.website/?sign={sign.lower()}&day=today"
        r = requests.post(url, timeout=5)
        if r.status_code == 200:
            return r.json()["description"], "en"
    except:
        return None, None
    return None, None

def fetch_from_turkish(sign):
    try:
        url = f"https://burc-yorumlari.vercel.app/get/{sign.lower()}"
        r = requests.get(url, timeout=5)
        if r.status_code == 200:
            d = r.json()
            if isinstance(d, list) and d:
                return d[0].get("GunlukYorum"), "tr"
    except:
        return None, None
    return None, None

@app.route("/translated-horoscope/<sign>", methods=["GET"])
def get_translated(sign):
    try:
        sources = [fetch_from_horoscope_app, fetch_from_aztro, fetch_from_turkish]
        text, lang = None, None
        for src in sources:
            text, lang = src(sign)
            if text:
                break
        if not text:
            return jsonify({"error": "No horoscope data available."}), 400

        if lang == "tr":
            return jsonify({"sign": sign.title(), "original": text, "translated": text})

        translated = client.chat.completions.create(
            model="gpt-3.5-turbo",
            messages=[
                {"role": "system", "content": "You are a helpful assistant who translates astrology texts into Turkish."},
                {"role": "user", "content": f"Translate this horoscope to Turkish:

{text}"}
            ]
        ).choices[0].message.content

        return jsonify({
            "sign": sign.title(),
            "original": text,
            "translated": translated
        })
    except Exception as e:
        return jsonify({"error": f"Translation failed: {str(e)}"}), 500

@app.route("/health", methods=["GET"])
def health():
    return jsonify({"status": "ok"})

if __name__ == "__main__":
    from waitress import serve
    port = int(os.environ.get("PORT", 5000))
    serve(app, host="0.0.0.0", port=port)
