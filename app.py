
from flask import Flask, request, jsonify
from openai import OpenAI
from skyfield.api import load, Topos
from datetime import datetime, timedelta
import os
import requests
import logging
import urllib.request

# Set up logging
logging.basicConfig(level=logging.INFO)

app = Flask(__name__)
client = OpenAI(api_key=os.getenv("OPENAI_API_KEY"))

# Download ephemeris file if not present
EPHEMERIS_PATH = "de440s.bsp"
EPHEMERIS_URL = "https://naif.jpl.nasa.gov/pub/naif/generic_kernels/spk/planets/de440s.bsp"

if not os.path.exists(EPHEMERIS_PATH):
    logging.info("Downloading ephemeris file...")
    urllib.request.urlretrieve(EPHEMERIS_URL, EPHEMERIS_PATH)
    logging.info("Download complete.")

ts = load.timescale()
eph = load(EPHEMERIS_PATH)

ZODIAC_SIGNS = [
    "Koç", "Boğa", "İkizler", "Yengeç", "Aslan", "Başak",
    "Terazi", "Akrep", "Yay", "Oğlak", "Kova", "Balık"
]

PLANETS = {
    "sun": eph["sun"],
    "moon": eph["moon"],
    "mercury": eph["mercury"],
    "venus": eph["venus"],
    "mars": eph["mars"],
    "jupiter": eph["jupiter barycenter"],
    "saturn": eph["saturn barycenter"]
}

PLANET_NAMES = {
    "sun": "Güneş", "moon": "Ay", "mercury": "Merkür", "venus": "Venüs", "mars": "Mars",
    "jupiter": "Jüpiter", "saturn": "Satürn"
}

ASPECTS = {
    "Conjunction": 0,
    "Opposition": 180,
    "Square": 90,
    "Trine": 120,
    "Sextile": 60
}

def get_zodiac_sign(degree):
    return ZODIAC_SIGNS[int(degree // 30) % 12]

def get_house(degree):
    return int(degree // 30) + 1

def angle_diff(a, b):
    diff = abs(a - b) % 360
    return min(diff, 360 - diff)

@app.route("/natal-chart", methods=["POST"])
def natal_chart():
    try:
        data = request.json
        date, time = data["date"], data["time"]
        lat, lon = float(data["lat"]), float(data["lon"])
        tz_offset = data.get("tz", "+00:00")
        dt_local = datetime.fromisoformat(f"{date}T{time}:00")
        hours_offset = int(tz_offset[:3])
        dt_utc = dt_local - timedelta(hours=hours_offset)
        t = ts.utc(dt_utc)

        observer = Topos(latitude_degrees=lat, longitude_degrees=lon)
        chart = []

        for key, body in PLANETS.items():
            astrometric = eph["earth"].at(t).observe(body)
            lon_deg = astrometric.apparent().ecliptic_latlon()[1].degrees
            sign = get_zodiac_sign(lon_deg)
            house = get_house(lon_deg)

            chart.append({
                "name": PLANET_NAMES[key],
                "sign": sign,
                "degree": round(lon_deg % 30, 2),
                "absolute_degree": round(lon_deg, 2),
                "retrograde": False,
                "house": house
            })

        aspects = []
        for i, p1 in enumerate(chart):
            for j, p2 in enumerate(chart):
                if i >= j: continue
                diff = angle_diff(p1["absolute_degree"], p2["absolute_degree"])
                for name, angle in ASPECTS.items():
                    if abs(diff - angle) <= 6:
                        aspects.append({
                            "between": f'{p1["name"]} & {p2["name"]}',
                            "aspect": name,
                            "orb": round(abs(diff - angle), 2)
                        })

        return jsonify({
            "chart": chart,
            "aspects": aspects,
            "date": date,
            "time": time,
            "timezone": tz_offset,
            "location": {"lat": lat, "lon": lon}
        })
    except Exception as e:
        return jsonify({"error": str(e)}), 400

@app.route("/translated-horoscope/<sign>", methods=["GET"])
def get_translated_horoscope(sign):
    try:
        url = f"https://burc-yorumlari.vercel.app/get/{sign.lower()}"
        response = requests.get(url, timeout=5)
        if response.status_code == 200:
            data = response.json()
            if isinstance(data, list) and data:
                return jsonify({
                    "sign": sign.title(),
                    "original": data[0].get("GunlukYorum"),
                    "translated": data[0].get("GunlukYorum")
                })

        url2 = f"https://aztro.sameerkumar.website/?sign={sign}&day=today"
        response2 = requests.post(url2)
        if response2.status_code == 200:
            description = response2.json().get("description", "")
            result = client.chat.completions.create(
                model="gpt-3.5-turbo",
                messages=[
                    {"role": "system", "content": "You are a helpful assistant who translates astrology texts into Turkish."},
                    {"role": "user", "content": f"Translate this horoscope to Turkish:\n\n{description}"}
                ]
            )
            translated = result.choices[0].message.content
            return jsonify({
                "sign": sign.title(),
                "original": description,
                "translated": translated
            })
        return jsonify({"error": "No horoscope found."}), 404
    except Exception as e:
        return jsonify({"error": str(e)}), 500

@app.route("/health")
def health():
    return jsonify({"status": "ok", "message": "API is up and running"})

if __name__ == "__main__":
    from waitress import serve
    port = int(os.environ.get("PORT", 5000))
    serve(app, host="0.0.0.0", port=port)
