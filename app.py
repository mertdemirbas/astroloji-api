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

# --- 1) İngilizce kaynak: Horoscope-App API ---
def fetch_from_horoscope_app_api(sign):
    try:
        url = f"https://horoscope-app-api.vercel.app/api/v1/get-horoscope/daily?sign={sign}&day=today"
        resp = requests.get(url, timeout=5)
        if resp.status_code == 200:
            data = resp.json().get("data", {})
            text = data.get("horoscope_data")
            if text:
                return text, "en"
    except:
        pass
    return None, None

# --- 2) İngilizce kaynak: Aztro API ---
def fetch_from_aztro(sign):
    try:
        url = f"https://aztro.sameerkumar.website/?sign={sign}&day=today"
        resp = requests.post(url, timeout=5)
        if resp.status_code == 200:
            text = resp.json().get("description")
            if text:
                return text, "en"
    except:
        pass
    return None, None

# --- 3) Türkçe kaynak: Burç-Yorumları API ---
def fetch_from_burc_yorumlari(sign):
    try:
        url = f"https://burc-yorumlari.vercel.app/get/{sign.lower()}"
        resp = requests.get(url, timeout=5)
        if resp.status_code == 200:
            data = resp.json()
            if isinstance(data, list) and data:
                text = data[0].get("GunlukYorum")
                if text:
                    return text, "tr"
    except:
        pass
    return None, None

@app.route("/translated-horoscope/<sign>", methods=["GET"])
def get_translated_horoscope(sign):
    sources = [
        fetch_from_horoscope_app_api,
        fetch_from_aztro,
        fetch_from_burc_yorumlari
    ]
    text, lang = None, None

    # Sırasıyla dene
    for src in sources:
        text, lang = src(sign)
        if text:
            break

    if not text:
        return jsonify({"error": "No horoscope data found from any provider."}), 400

    # Zaten Türkçe ise direkt döndür
    if lang == "tr":
        return jsonify({
            "sign": sign.title(),
            "original": text,
            "translated": text
        })

    # İngilizce → Türkçe çeviri
    response = client.chat.completions.create(
        model="gpt-3.5-turbo",
        messages=[
            {"role": "system", "content": "You are a helpful assistant who translates astrology texts into Turkish."},
            {"role": "user", "content": f"Translate this horoscope to Turkish:\n\n{text}"}
        ]
    )
    translated = response.choices[0].message.content.strip()

    return jsonify({
        "sign": sign.title(),
        "original": text,
        "translated": translated
    })


# --- Natal chart hesaplama ---
@app.route("/natal-chart", methods=["POST"])
def natal_chart():
    try:
        data = request.json or {}
        date_raw = data.get("date", "")    # "YYYY-MM-DD"
        time = data.get("time", "")        # "HH:MM"
        lat = float(data.get("lat", 0))
        lon = float(data.get("lon", 0))
        tz_raw = data.get("tz", "+00:00")  # "+03:00" veya "3"

        # flatlib’in istediği format: "YYYY/MM/DD"
        date = date_raw.replace("-", "/")

        # timezone’u integer saate dönüştür
        tz = int(tz_raw.split(":")[0]) if ":" in tz_raw else int(tz_raw)

        # GeoPos için lat/lon string
        pos = GeoPos(str(lat), str(lon))

        # Datetime objesi
        dt = Datetime(date, time, tz)

        # Chart ve gezegenler
        chart = Chart(dt, pos)
        bodies = [
            const.SUN, const.MOON, const.MERCURY, const.VENUS,
            const.MARS, const.JUPITER, const.SATURN,
            const.URANUS, const.NEPTUNE, const.PLUTO,
            const.ASC, const.MC
        ]

        result = []
        for b in bodies:
            o = chart.get(b)
            result.append({
                "name": o.id,
                "sign": o.sign,
                "house": o.house,
                "degree": round(o.lon % 30, 2),
                "absolute_degree": round(o.lon, 2),
                "retrograde": o.retrograde
            })

        return jsonify({
            "chart": result,
            "date": date_raw,
            "time": time,
            "timezone": tz_raw,
            "location": {"lat": lat, "lon": lon}
        })

    except Exception as e:
        return jsonify({"error": str(e)}), 500


if __name__ == "__main__":
    port = int(os.environ.get("PORT", 5000))
    app.run(host="0.0.0.0", port=port)
