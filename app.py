from flask import Flask, request, jsonify
from flask_cors import CORS
import swisseph as swe
import datetime

app = Flask(__name__)
CORS(app)

# Swiss Ephemeris veri dosyalarının yolu
swe.set_ephe_path("./ephe")

# Hesaplanacak gezegenler
PLANETS = {
    'Sun': swe.SUN,
    'Moon': swe.MOON,
    'Mercury': swe.MERCURY,
    'Venus': swe.VENUS,
    'Mars': swe.MARS,
    'Jupiter': swe.JUPITER,
    'Saturn': swe.SATURN
}

@app.route("/natal-chart", methods=["POST"])
def natal_chart():
    data = request.json
    try:
        date = data["date"]
        time = data["time"]
        lat = float(data["lat"])
        lon = float(data["lon"])

        year, month, day = map(int, date.split("-"))
        hour, minute = map(int, time.split(":"))
        decimal_hour = hour + minute / 60.0

        jd = swe.julday(year, month, day, decimal_hour)

        positions = {}
        for name, planet_id in PLANETS.items():
            lon, _ = swe.calc_ut(jd, planet_id)  # sadece iki değer döner (lon, info)
            positions[name] = round(lon, 2)

        return jsonify({
            "julian_day": jd,
            "planets": positions
        })
    except Exception as e:
        return jsonify({"error": str(e)}), 400

@app.route("/horoscope/today/<sign>", methods=["GET"])
def daily_horoscope(sign):
    today = datetime.datetime.utcnow()
    jd = swe.julday(today.year, today.month, today.day)
    sun_pos = swe.calc_ut(jd, swe.SUN)[0]  # sadece dereceyi al

    sun_sign = get_sun_sign(sun_pos)

    if sign.lower() != sun_sign.lower():
        message = f"Güneş bugün {sun_sign} burcunda, fakat senin burcun {sign.title()}."
    else:
        message = f"Bugün Güneş senin burcunda ({sign.title()}), bu enerji seni destekliyor!"

    return jsonify({
        "sun_position": round(sun_pos, 2),
        "sun_sign": sun_sign,
        "message": message
    })

def get_sun_sign(lon):
    signs = [
        "Aries", "Taurus", "Gemini", "Cancer", "Leo", "Virgo",
        "Libra", "Scorpio", "Sagittarius", "Capricorn", "Aquarius", "Pisces"
    ]
    index = int(lon / 30) % 12
    return signs[index]

if __name__ == "__main__":
    import os
    port = int(os.environ.get("PORT", 5000))
    app.run(debug=True, host="0.0.0.0", port=port)
