
from flask import Flask, request, jsonify
from openai import OpenAI
from skyfield.api import load, wgs84
from datetime import datetime, timedelta
import os
import requests
import logging

# Setup logging
logging.basicConfig(level=logging.INFO)
logger = logging.getLogger(__name__)

app = Flask(__name__)
client = OpenAI(api_key=os.getenv("OPENAI_API_KEY"))

ts = load.timescale()
EPHEMERIS_PATH = "de440s.bsp"

def download_ephemeris():
    url = "https://naif.jpl.nasa.gov/pub/naif/generic_kernels/spk/planets/de440s.bsp"
    os.makedirs("skyfield_data", exist_ok=True)
    filepath = os.path.join("skyfield_data", EPHEMERIS_PATH)
    if not os.path.exists(filepath):
        logger.info("Downloading ephemeris file...")
        with open(filepath, "wb") as f:
            f.write(requests.get(url).content)
    return filepath

def get_zodiac(deg):
    signs = ["Koç", "Boğa", "İkizler", "Yengeç", "Aslan", "Başak",
             "Terazi", "Akrep", "Yay", "Oğlak", "Kova", "Balık"]
    return signs[int(deg // 30) % 12]

@app.route("/natal-chart", methods=["POST"])
def natal_chart():
    try:
        data = request.json
        date = data["date"]
        time = data["time"]
        lat = float(data["lat"])
        lon = float(data["lon"])
        tz = data.get("tz", "+00:00")

        tz_hour = int(tz[:3])
        dt = datetime.fromisoformat(f"{date}T{time}:00") - timedelta(hours=tz_hour)
        eph_path = download_ephemeris()
        eph = load(Path(eph_path))
        t = ts.utc(dt.year, dt.month, dt.day, dt.hour, dt.minute)

        planets = ["sun", "moon", "mercury", "venus", "mars",
                   "jupiter", "saturn", "uranus", "neptune", "pluto"]
        chart = []
        for planet in planets:
            body = eph[planet]
            astrometric = eph["earth"].at(t).observe(body).apparent()
            lon_deg = astrometric.ecliptic_latlon()[1].degrees
            chart.append({
                "name": planet.title(),
                "degree": round(lon_deg % 30, 2),
                "sign": get_zodiac(lon_deg)
            })

        return jsonify({
            "chart": chart,
            "date": date,
            "time": time,
            "timezone": tz
        })
    except Exception as e:
        return jsonify({"error": str(e)}), 400

def fetch_from_burc_yorumlari(sign):
    try:
        url = f"https://burc-yorumlari.vercel.app/get/{sign.lower()}"
        response = requests.get(url, timeout=5)
        if response.status_code == 200:
            data = response.json()
            if isinstance(data, list) and data:
                return data[0].get("GunlukYorum"), "tr"
    except:
        return None, None
    return None, None

def fetch_from_aztro(sign):
    try:
        url = f"https://aztro.sameerkumar.website/?sign={sign.lower()}&day=today"
        response = requests.post(url)
        if response.status_code == 200:
            data = response.json()
            return data.get("description"), "en"
    except:
        return None, None
    return None, None

@app.route("/translated-horoscope/<sign>", methods=["GET"])
def get_translated_horoscope(sign):
    try:
        sources = [fetch_from_burc_yorumlari, fetch_from_aztro]
        text, lang = None, None

        for source in sources:
            text, lang = source(sign)
            if text:
                break

        if not text:
            return jsonify({"error": "No horoscope data found."}), 400

        if lang == "tr":
            return jsonify({
                "sign": sign.title(),
                "original": text,
                "translated": text
            })

        response = client.chat.completions.create(
            model="gpt-3.5-turbo",
            messages=[
                {"role": "system", "content": "You are a helpful assistant who translates astrology texts into Turkish."},
                {"role": "user", "content": f"Translate this horoscope to Turkish:

{text}"}
            ]
        )
        translated = response.choices[0].message.content

        return jsonify({
            "sign": sign.title(),
            "original": text,
            "translated": translated
        })
    except Exception as e:
        return jsonify({"error": f"Translation failed: {str(e)}"}), 500

@app.route("/health", methods=["GET"])
def health_check():
    return jsonify({"status": "ok", "timestamp": datetime.now().isoformat()})

if __name__ == "__main__":
    from waitress import serve
    port = int(os.environ.get("PORT", 5000))
    serve(app, host="0.0.0.0", port=port)
