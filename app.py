from flask import Flask, jsonify, request
import os
import requests
from openai import OpenAI
from datetime import datetime, timedelta, timezone
from skyfield.api import load, Topos

app = Flask(__name__)
client = OpenAI(api_key=os.getenv("OPENAI_API_KEY"))

# ---------- Günlük Burç Yorumları ----------

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

# ---------- Doğum Haritası ----------

@app.route("/natal-chart", methods=["POST"])
def natal_chart():
    try:
        data = request.json
        date = data.get("date")
        time = data.get("time")
        lat = float(data.get("lat"))
        lon = float(data.get("lon"))
        tz_offset = data.get("tz", "+03:00")

        # Saat dilimini çöz
        sign = 1 if '+' in tz_offset else -1
        hours = int(tz_offset[1:3])
        minutes = int(tz_offset[4:6])
        offset = timedelta(hours=sign * hours, minutes=sign * minutes)
        tz = timezone(offset)

        dt = datetime.strptime(f"{date} {time}", "%Y-%m-%d %H:%M").replace(tzinfo=tz)
        ts = load.timescale()
        t = ts.from_datetime(dt)

        eph = load('de421.bsp')
        observer = eph['earth'] + Topos(latitude_degrees=lat, longitude_degrees=lon)

        planet_keys = [
            "sun", "moon", "mercury", "venus", "mars",
            "jupiter barycenter", "saturn barycenter",
            "uranus barycenter", "neptune barycenter", "pluto barycenter"
        ]

        planet_names = {
            "sun": "Güneş", "moon": "Ay", "mercury": "Merkür", "venus": "Venüs", "mars": "Mars",
            "jupiter barycenter": "Jüpiter", "saturn barycenter": "Satürn", "uranus barycenter": "Uranüs",
            "neptune barycenter": "Neptün", "pluto barycenter": "Plüton"
        }

        zodiac_signs = [
            "Koç", "Boğa", "İkizler", "Yengeç", "Aslan", "Başak",
            "Terazi", "Akrep", "Yay", "Oğlak", "Kova", "Balık"
        ]

        chart = []
        for key in planet_keys:
            body = eph[key]
            astrometric = observer.at(t).observe(body).apparent()
            lon = astrometric.ecliptic_latlon()[1].degrees
            sign_index = int(lon / 30) % 12
            retro = lon < observer.at(t - timedelta(days=1)).observe(body).apparent().ecliptic_latlon()[1].degrees

            chart.append({
                "name": planet_names[key],
                "sign": zodiac_signs[sign_index],
                "degree": round(lon % 30, 2),
                "retrograde": bool(retro)
            })

        return jsonify({
            "chart": chart,
            "date": date,
            "time": time,
            "timezone": tz_offset
        })

    except Exception as e:
        return jsonify({"error": str(e)}), 400

if __name__ == "__main__":
    port = int(os.environ.get("PORT", 5000))
    app.run(host="0.0.0.0", port=port)
