# app.py
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

# --- 1) Günlük Burç Yorumu Endpoint -------------------------------------

def fetch_from_horoscope_app_api(sign):
    url = f"https://horoscope-app-api.vercel.app/api/v1/get-horoscope/daily?sign={sign}&day=today"
    r = requests.get(url, timeout=5)
    if r.status_code == 200:
        data = r.json().get("data", {})
        return data.get("horoscope_data"), "en"
    return None, None

def fetch_from_aztro_api(sign):
    url = f"https://aztro.sameerkumar.website/?sign={sign}&day=today"
    r = requests.post(url, timeout=5)
    if r.status_code == 200:
        return r.json().get("description"), "en"
    return None, None

def fetch_from_burc_yorumlari(sign):
    url = f"https://burc-yorumlari.vercel.app/get/{sign.lower()}"
    r = requests.get(url, timeout=5)
    if r.status_code == 200:
        data = r.json()
        if isinstance(data, list) and data:
            return data[0].get("GunlukYorum"), "tr"
    return None, None

@app.route("/translated-horoscope/<sign>", methods=["GET"])
def get_translated_horoscope(sign):
    # 1) İngilizce kaynaklar
    for fn in (fetch_from_horoscope_app_api, fetch_from_aztro_api):
        text, lang = fn(sign)
        if text:
            # İngilizce → Türkçe
            resp = client.chat.completions.create(
                model="gpt-3.5-turbo",
                messages=[
                    {"role": "system", "content": "You are an assistant who translates horoscope texts to Turkish."},
                    {"role": "user", "content": text}
                ]
            )
            return jsonify({
                "sign": sign.title(),
                "original": text,
                "translated": resp.choices[0].message.content
            })
    # 2) Türkçe kaynak
    text, lang = fetch_from_burc_yorumlari(sign)
    if text:
        return jsonify({
            "sign": sign.title(),
            "original": text,
            "translated": text
        })
    return jsonify({"error": "No horoscope data available"}), 400


# --- 2) Natal Chart Endpoint ---------------------------------------------

ZODIAC_SIGNS = [
    "Koç", "Boğa", "İkizler", "Yengeç", "Aslan", "Başak",
    "Terazi", "Akrep", "Yay", "Oğlak", "Kova", "Balık"
]
ASPECTS = {
    "Conjunction":   0,
    "Opposition": 180,
    "Square":       90,
    "Trine":       120,
    "Sextile":      60,
}

def get_zodiac_sign(deg):
    return ZODIAC_SIGNS[int(deg//30) % 12]

def get_house(deg):
    return int(deg//30) + 1

def angle_diff(a, b):
    d = abs(a - b) % 360
    return d if d <= 180 else 360 - d

def find_aspects(planets, orb=6):
    out = []
    n = len(planets)
    for i in range(n):
        for j in range(i+1, n):
            d = angle_diff(planets[i]["abs_deg"], planets[j]["abs_deg"])
            for name, target in ASPECTS.items():
                if abs(d - target) <= orb:
                    out.append({
                        "between": f'{planets[i]["name"]} & {planets[j]["name"]}',
                        "aspect": name,
                        "orb": round(abs(d - target),2)
                    })
    return out

@app.route("/natal-chart", methods=["POST"])
def natal_chart():
    data = request.get_json(force=True)
    date = data.get("date")    # "1994-09-15"
    time = data.get("time")    # "15:30"
    lat  = data.get("lat")     # 41.0082
    lon  = data.get("lon")     # 28.9784
    tz   = data.get("tz", "+00:00")  # "+03:00"

    # Flatlib Datetime expects date, time, tz
    dt = Datetime(date, time, tz)
    pos = GeoPos(str(lat), str(lon))
    chart = Chart(dt, pos)

    bodies = [
        const.SUN, const.MOON, const.MERCURY, const.VENUS, const.MARS,
        const.JUPITER, const.SATURN, const.URANUS, const.NEPTUNE, const.PLUTO
    ]

    result = []
    for b in bodies:
        obj = chart.get(b)
        deg = obj.lon  # ekliptik boylam derecesi
        result.append({
            "name":       obj.id.title(),
            "sign":       get_zodiac_sign(deg),
            "degree":     round(deg % 30, 2),
            "abs_deg":    round(deg,      2),
            "house":      obj.house,
            "retrograde": obj.retrograde
        })

    aspects = find_aspects(result)

    return jsonify({
        "chart":   result,
        "aspects": aspects,
        "date":    date,
        "time":    time,
        "timezone": tz,
        "location": {"lat": lat, "lon": lon}
    })


if __name__ == "__main__":
    # production WSGI
    from waitress import serve
    port = int(os.environ.get("PORT", 5000))
    serve(app, host="0.0.0.0", port=port)
