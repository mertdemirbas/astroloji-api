from flask import Flask, request, jsonify
from openai import OpenAI
from skyfield.api import load, Topos
from datetime import datetime, timedelta
import os
import requests
import logging

app = Flask(__name__)
client = OpenAI(api_key=os.getenv("OPENAI_API_KEY"))
logging.basicConfig(level=logging.INFO)

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
    return ZODIAC_SIGNS[int(degree // 30) % 12]

def get_house(degree):
    return int(degree // 30) + 1

def angle_difference(a1, a2):
    diff = abs(a1 - a2) % 360
    return min(diff, 360 - diff)

def find_aspects(planets):
    results = []
    for i, p1 in enumerate(planets):
        for j, p2 in enumerate(planets):
            if i >= j:
                continue
            diff = angle_difference(p1["absolute_degree"], p2["absolute_degree"])
            for name, target in ASPECTS.items():
                if abs(diff - target) <= 6:
                    results.append({
                        "between": f'{p1["name"]} & {p2["name"]}',
                        "aspect": name,
                        "orb": round(abs(diff - target), 2)
                    })
    return results

def parse_timezone(tz_raw):
    sign = 1 if tz_raw[0] == '+' else -1
    hours = int(tz_raw[1:3])
    minutes = int(tz_raw[4:6]) if len(tz_raw) > 5 else 0
    return sign * (hours + minutes / 60)

@app.route("/natal-chart", methods=["POST"])
def natal_chart():
    try:
        data = request.json
        date = data["date"]
        time = data["time"]
        lat = float(data["lat"])
        lon = float(data["lon"])
        tz = data.get("tz", "+00:00")
        tz_offset = parse_timezone(tz)

        dt = datetime.fromisoformat(f"{date}T{time}:00") - timedelta(hours=tz_offset)

        ts = load.timescale()
        eph = load('de440s.bsp')
        t = ts.utc(dt.year, dt.month, dt.day, dt.hour, dt.minute)

        earth = eph["earth"]
        planets = ["sun", "moon", "mercury", "venus", "mars", "jupiter", "saturn"]
        names = ["Güneş", "Ay", "Merkür", "Venüs", "Mars", "Jüpiter", "Satürn"]

        chart = []
        for key, name in zip(planets, names):
            astrometric = earth.at(t).observe(eph[key])
            ecl = astrometric.apparent().ecliptic_latlon()
            lon_deg = ecl[1].degrees
            chart.append({
                "name": name,
                "sign": get_zodiac_sign(lon_deg),
                "degree": round(lon_deg % 30, 2),
                "absolute_degree": round(lon_deg, 2),
                "retrograde": "false",
                "house": get_house(lon_deg)
            })

        aspects = find_aspects(chart)

        return jsonify({
            "chart": chart,
            "aspects": aspects,
            "date": date,
            "time": time,
            "timezone": tz,
            "location": {"lat": lat, "lon": lon}
        })
    except Exception as e:
        return jsonify({"error": str(e)}), 400

def fetch_from_aztro(sign):
    try:
        url = f"https://aztro.sameerkumar.website/?sign={sign}&day=today"
        response = requests.post(url)
        if response.status_code == 200:
            return response.json().get("description"), "en"
    except:
        pass
    return None, None

def fetch_from_horoscope_api(sign):
    try:
        url = f"https://horoscope-app-api.vercel.app/api/v1/get-horoscope/daily?sign={sign.lower()}"
        response = requests.get(url)
        if response.status_code == 200:
            data = response.json()
            return data.get("data", {}).get("horoscope_data", {}).get("daily", {}).get("general", {}).get("description"), "en"
    except:
        pass
    return None, None

def fetch_from_burc_yorumlari(sign):
    try:
        url = f"https://burc-yorumlari.vercel.app/get/{sign.lower()}"
        response = requests.get(url)
        if response.status_code == 200:
            data = response.json()
            if isinstance(data, list) and data:
                return data[0].get("GunlukYorum"), "tr"
    except:
        pass
    return None, None

@app.route("/translated-horoscope/<sign>", methods=["GET"])
def get_translated_horoscope(sign):
    sources = [fetch_from_aztro, fetch_from_horoscope_api, fetch_from_burc_yorumlari]
    text, lang = None, None
    for source in sources:
        text, lang = source(sign)
        if text:
            break

    if not text:
        return jsonify({"error": "No horoscope data found."}), 404

    if lang == "tr":
        return jsonify({
            "sign": sign.title(),
            "original": text,
            "translated": text
        })

    try:
        response = client.chat.completions.create(
            model="gpt-3.5-turbo",
            messages=[
                {"role": "system", "content": "You are a helpful assistant who translates astrology texts into Turkish."},
                {"role": "user", "content": f"Translate this horoscope to Turkish:\n\n{text}"}
            ]
        )
        translated = response.choices[0].message.content
    except Exception as e:
        translated = f"(Translation failed) {text}"

    return jsonify({
        "sign": sign.title(),
        "original": text,
        "translated": translated
    })

if __name__ == "__main__":
    from waitress import serve
    port = int(os.environ.get("PORT", 5000))
    serve(app, host="0.0.0.0", port=port)
