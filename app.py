from flask import Flask, jsonify, request
import os
import requests
from openai import OpenAI
from skyfield.api import load, Topos
from timezonefinder import TimezoneFinder
from datetime import datetime
import pytz

app = Flask(__name__)
client = OpenAI(api_key=os.getenv("OPENAI_API_KEY"))

# Horoscope kaynakları
def fetch_from_horoscope_app_api(sign):
    try:
        url = f"https://horoscope-app-api.vercel.app/api/v1/get-horoscope/daily?sign={sign}&day=today"
        response = requests.get(url, timeout=5)
        if response.status_code == 200:
            data = response.json()
            return data.get("data", {}).get("horoscope_data"), "en"
    except:
        return None, None
    return None, None

def fetch_from_aztro_api(sign):
    try:
        url = f"https://aztro.sameerkumar.website/?sign={sign}&day=today"
        response = requests.post(url, timeout=5)
        if response.status_code == 200:
            data = response.json()
            return data.get("description"), "en"
    except:
        return None, None
    return None, None

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

@app.route("/translated-horoscope/<sign>", methods=["GET"])
def get_translated_horoscope(sign):
    try:
        sources = [fetch_from_horoscope_app_api, fetch_from_aztro_api, fetch_from_burc_yorumlari]
        text, lang = None, None

        for source in sources:
            text, lang = source(sign)
            if text:
                break

        if not text:
            return jsonify({"error": "No horoscope data returned from any provider."}), 400

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


# Skyfield setup
ephemeris = load('de421.bsp')
planets = {
    "Sun": ephemeris['sun'],
    "Moon": ephemeris['moon'],
    "Mercury": ephemeris['mercury'],
    "Venus": ephemeris['venus'],
    "Mars": ephemeris['mars'],
    "Jupiter": ephemeris['jupiter barycenter'],
    "Saturn": ephemeris['saturn barycenter'],
    "Uranus": ephemeris['uranus barycenter'],
    "Neptune": ephemeris['neptune barycenter'],
    "Pluto": ephemeris['pluto barycenter'],
}

ZODIAC_SIGNS = [
    "Aries", "Taurus", "Gemini", "Cancer", "Leo", "Virgo",
    "Libra", "Scorpio", "Sagittarius", "Capricorn", "Aquarius", "Pisces"
]

def degree_to_sign(degree):
    index = int(degree // 30) % 12
    sign = ZODIAC_SIGNS[index]
    degree_in_sign = degree % 30
    return sign, round(degree_in_sign, 2)

@app.route("/natal-chart", methods=["POST"])
def natal_chart():
    try:
        data = request.json
        date = data.get("date")
        time = data.get("time")
        lat = float(data.get("lat"))
        lon = float(data.get("lon"))

        tf = TimezoneFinder()
        tz_str = tf.timezone_at(lat=lat, lng=lon)
        if tz_str is None:
            tz_str = 'UTC'
        timezone = pytz.timezone(tz_str)

        dt = datetime.strptime(f"{date} {time}", "%Y-%m-%d %H:%M")
        dt = timezone.localize(dt)

        ts = load.timescale()
        t = ts.from_datetime(dt)
        observer = Topos(latitude_degrees=lat, longitude_degrees=lon)

        result = []
        for name, body in planets.items():
            astrometric = ephemeris['earth'].at(t).observe(body).apparent()
            ecliptic = astrometric.ecliptic_latlon()
            lon_deg = ecliptic[1].degrees
            sign, deg = degree_to_sign(lon_deg)

            result.append({
                "name": name,
                "sign": sign,
                "degree": deg
            })

        return jsonify({
            "chart": result,
            "datetime": dt.isoformat(),
            "timezone": tz_str
        })

    except Exception as e:
        return jsonify({"error": str(e)}), 400


if __name__ == "__main__":
    port = int(os.environ.get("PORT", 5000))
    app.run(host="0.0.0.0", port=port)
