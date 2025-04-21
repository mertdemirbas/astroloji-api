from flask import Flask, jsonify, request
import os
import requests
from openai import OpenAI
from skyfield.api import load, Topos
from skyfield.api import N, E
from skyfield.api import Star
from skyfield import almanac
from skyfield.data import mpc
from skyfield.positionlib import position_of_radec
from datetime import datetime
import pytz

app = Flask(__name__)
client = OpenAI(api_key=os.getenv("OPENAI_API_KEY"))

# ---------- 1. Günlük Burç Yorumları ----------

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

# ---------- 2. Doğum Haritası Hesaplama (Skyfield ile) ----------

@app.route("/natal-chart", methods=["POST"])
def natal_chart():
    try:
        data = request.json
        date = data.get("date")  # "1994-09-15"
        time = data.get("time")  # "15:30"
        lat = float(data.get("lat"))  # 41.0082
        lon = float(data.get("lon"))  # 28.9784
        tz_str = data.get("tz", "+03:00")  # "+03:00"

        # Timezone dönüşümü
        tz_offset = int(tz_str.replace("+", "").split(":")[0])
        tz = pytz.FixedOffset(tz_offset * 60)
        dt = datetime.strptime(f"{date} {time}", "%Y-%m-%d %H:%M")
        dt = tz.localize(dt)

        # Skyfield yüklemeleri
        eph = load('de421.bsp')
        planets = eph
        ts = load.timescale()
        t = ts.from_datetime(dt)

        location = Topos(latitude_degrees=lat, longitude_degrees=lon)

        observer = eph['earth'] + location

        planet_list = {
            'Sun': 'sun',
            'Moon': 'moon',
            'Mercury': 'mercury',
            'Venus': 'venus',
            'Mars': 'mars',
            'Jupiter': 'jupiter barycenter',
            'Saturn': 'saturn barycenter',
            'Uranus': 'uranus barycenter',
            'Neptune': 'neptune barycenter',
            'Pluto': 'pluto barycenter'
        }

        chart = []

        for name, target in planet_list.items():
            planet = eph[target]
            astrometric = observer.at(t).observe(planet).apparent()
            ecl = astrometric.ecliptic_latlon()
            lon_deg = round(ecl[1].degrees, 2)

            # Retrograde kontrolü: geçmişteki konuma göre ileride mi?
            past_t = ts.from_datetime(dt - timedelta(days=5))
            past_ast = observer.at(past_t).observe(planet).apparent()
            past_lon = past_ast.ecliptic_latlon()[1].degrees
            retro = lon_deg < past_lon

            sign = zodiac_sign(lon_deg)

            chart.append({
                "name": name,
                "sign": sign,
                "degree": lon_deg,
                "retrograde": retro
            })

        return jsonify({
            "chart": chart,
            "date": date,
            "time": time,
            "timezone": tz_str
        })

    except Exception as e:
        return jsonify({"error": str(e)}), 400

# ---------- Yardımcı Fonksiyonlar ----------

def zodiac_sign(degree):
    signs = [
        "Koç", "Boğa", "İkizler", "Yengeç", "Aslan", "Başak",
        "Terazi", "Akrep", "Yay", "Oğlak", "Kova", "Balık"
    ]
    return signs[int(degree / 30) % 12]

# ---------- Sunucu ----------

if __name__ == "__main__":
    port = int(os.environ.get("PORT", 5000))
    app.run(host="0.0.0.0", port=port)
