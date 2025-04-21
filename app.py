from flask import Flask, jsonify, request
import os
import requests
from openai import OpenAI
from flatlib.chart import Chart
from flatlib.datetime import Datetime
from flatlib.geopos import GeoPos
from flatlib import const

app = Flask(__name__)
client = OpenAI(api_key=os.getenv("OPENAI_API_KEY"))

# 1. Horoscope App API (İngilizce)
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

# 2. Aztro API (İngilizce)
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

# 3. Türkçe kaynak
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

@app.route("/natal-chart", methods=["POST"])
def natal_chart():
    try:
        data = request.json
        date = data.get("date")  # Örn: "1994-09-15"
        time = data.get("time")  # Örn: "15:30"
        
        # Enlem ve boylam değerlerini düzgün formatta hazırla
        lat = data.get("lat")
        lon = data.get("lon")
        
        # Tz string olarak gelirse +03:00 veya "3" gibi, int'e çevrilir
        tz_raw = data.get("tz", "+03:00")
        if isinstance(tz_raw, str) and ":" in tz_raw:
            tz = int(tz_raw.replace("+", "").split(":")[0])
        else:
            tz = int(str(tz_raw).replace("+", ""))
        
        # GeoPos için değerleri tam sayı ve ondalık olarak ayırın
        lat_deg = int(float(lat))
        lat_min = int((float(lat) - lat_deg) * 60)
        lon_deg = int(float(lon))
        lon_min = int((float(lon) - lon_deg) * 60)
        
        # Doğu/batı, kuzey/güney belirle
        lat_ns = "N" if float(lat) >= 0 else "S"
        lon_ew = "E" if float(lon) >= 0 else "W"
        
        # GeoPos formatına dönüştür: derece°dakika'yön
        lat_str = f"{abs(lat_deg)}°{lat_min}'{lat_ns}"
        lon_str = f"{abs(lon_deg)}°{lon_min}'{lon_ew}"
        
        location = GeoPos(lat_str, lon_str)
        dt = Datetime(date, time, tz)
        chart = Chart(dt, location)
        planets = [
            const.SUN, const.MOON, const.MERCURY, const.VENUS, const.MARS,
            const.JUPITER, const.SATURN, const.URANUS, const.NEPTUNE, const.PLUTO,
            const.ASC, const.MC
        ]
        result = []
        for obj_name in planets:
            obj = chart.get(obj_name)
            result.append({
                "name": obj.id,
                "sign": obj.sign,
                "house": obj.house,
                "longitude": obj.lon,
                "retrograde": obj.retrograde
            })
        return jsonify({
            "chart": result,
            "date": date,
            "time": time,
            "timezone": tz
        })
    except Exception as e:
        return jsonify({"error": str(e)}), 400

if __name__ == "__main__":
    port = int(os.environ.get("PORT", 5000))
    app.run(host="0.0.0.0", port=port)
