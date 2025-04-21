from flask import Flask, request, jsonify
from skyfield.api import load, Topos, Loader
from datetime import datetime, timedelta
import os
import requests
from openai import OpenAI

# Flask app
app = Flask(__name__)

# OpenAI istemcisi
client = OpenAI(api_key=os.getenv("OPENAI_API_KEY"))

# Skyfield loader ile runtime'da indirme
skyfield_loader = Loader('./skyfield_data')
eph = skyfield_loader('de440s.bsp')
ts = skyfield_loader.timescale()

# Gezegenler ve burçlar
PLANET_NAMES = {
    "sun": "Güneş", "moon": "Ay", "mercury": "Merkür", "venus": "Venüs", "mars": "Mars",
    "jupiter": "Jüpiter", "saturn": "Satürn", "uranus": "Uranüs", "neptune": "Neptün", "pluto": "Plüton"
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


def get_zodiac_sign(degree):
    index = int(degree // 30) % 12
    return ZODIAC_SIGNS[index]

def get_house(degree):
    return int(degree // 30) + 1

def angle_difference(a1, a2):
    diff = abs(a1 - a2) % 360
    return diff if diff <= 180 else 360 - diff

def find_aspects(planets):
    result = []
    tolerance = 6
    for i, p1 in enumerate(planets):
        for j, p2 in enumerate(planets):
            if i >= j:
                continue
            diff = angle_difference(p1["degree"], p2["degree"])
            for name, target in ASPECTS.items():
                if abs(diff - target) <= tolerance:
                    result.append({
                        "between": f'{p1["name"]} & {p2["name"]}',
                        "aspect": name,
                        "orb": round(abs(diff - target), 2)
                    })
    return result


@app.route("/natal-chart", methods=["POST"])
def natal_chart():
    try:
        data = request.json
        date = data.get("date")
        time = data.get("time")
        lat = float(data.get("lat"))
        lon = float(data.get("lon"))
        tz_offset = data.get("tz", "+03:00")

        # Zaman dönüşümü UTC'ye
        dt = datetime.fromisoformat(f"{date}T{time}:00")
        offset_hours = int(tz_offset.replace("+", "").replace(":", ""))
        dt_utc = dt - timedelta(hours=offset_hours)

        t = ts.utc(dt_utc.year, dt_utc.month, dt_utc.day, dt_utc.hour, dt_utc.minute)
        observer = Topos(latitude_degrees=lat, longitude_degrees=lon)

        planet_keys = ["sun", "moon", "mercury", "venus", "mars", "jupiter", "saturn", "uranus", "neptune", "pluto"]
        chart = []

        for key in planet_keys:
            body = eph[key]
            astrometric = eph["earth"].at(t).observe(body).apparent()
            lon_deg = astrometric.ecliptic_latlon()[1].degrees
            prev_lon_deg = eph["earth"].at(t - timedelta(days=1)).observe(body).apparent().ecliptic_latlon()[1].degrees
            retro = lon_deg < prev_lon_deg

            chart.append({
                "name": PLANET_NAMES[key],
                "sign": get_zodiac_sign(lon_deg),
                "degree": round(lon_deg % 30, 2),
                "retrograde": retro,
                "house": get_house(lon_deg)
            })

        aspects = find_aspects(chart)

        return jsonify({
            "chart": chart,
            "aspects": aspects,
            "date": date,
            "time": time,
            "timezone": tz_offset
        })

    except Exception as e:
        return jsonify({"error": str(e)}), 400

# Günlük burç yorumu kaynakları
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
        url = f"https://aztro.sameerkumar.website/?sign={sign}&day=today"
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
                {"role": "user", "content": f"Translate this horoscope to Turkish:\n\n{text}"}
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

# Prod ortamı için
if __name__ == "__main__":
    from waitress import serve
    port = int(os.environ.get("PORT", 5000))
    serve(app, host="0.0.0.0", port=port)
