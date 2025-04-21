from flask import Flask, request, jsonify
from openai import OpenAI
from skyfield.api import load, Topos
from datetime import datetime, timedelta
import os
import requests
import logging

# Set up logging
logging.basicConfig(level=logging.INFO, format='%(asctime)s - %(levelname)s - %(message)s')

app = Flask(__name__)
client = OpenAI(api_key=os.getenv("OPENAI_API_KEY"))
ts = load.timescale()

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

PLANET_MAPPINGS = {
    'MERCURY BARYCENTER': 'Merkür', 'VENUS BARYCENTER': 'Venüs', 'EARTH BARYCENTER': 'Dünya',
    'MARS BARYCENTER': 'Mars', 'JUPITER BARYCENTER': 'Jüpiter', 'SATURN BARYCENTER': 'Satürn',
    'SUN': 'Güneş', 'MOON': 'Ay',
    'MERCURY': 'Merkür', 'VENUS': 'Venüs', 'EARTH': 'Dünya',
    'MARS': 'Mars', 'JUPITER': 'Jüpiter', 'SATURN': 'Satürn'
}

def get_zodiac_sign(degree):
    return ZODIAC_SIGNS[int(degree // 30) % 12]

def get_house(degree):
    return int(degree // 30) + 1

def angle_difference(a1, a2):
    diff = abs(a1 - a2) % 360
    return min(diff, 360 - diff)

def find_aspects(planets):
    result = []
    tolerance = 6
    for i, p1 in enumerate(planets):
        if p1.get("error"): continue
        for j, p2 in enumerate(planets):
            if i >= j or p2.get("error"): continue
            diff = angle_difference(float(p1["absolute_degree"]), float(p2["absolute_degree"]))
            for name, target in ASPECTS.items():
                if abs(diff - target) <= tolerance:
                    result.append({
                        "between": f'{p1["name"]} & {p2["name"]}',
                        "aspect": name,
                        "orb": round(abs(diff - target), 2)
                    })
    return result

def parse_timezone(tz_raw):
    try:
        sign = 1 if tz_raw[0] == '+' else -1
        hours = int(tz_raw[1:3])
        minutes = int(tz_raw[4:6]) if len(tz_raw) > 5 else 0
        return sign * (hours + minutes / 60)
    except:
        return 0

def calculate_chart(date_utc):
    try:
        eph = load('de440s.bsp')
        t = ts.utc(date_utc.year, date_utc.month, date_utc.day, date_utc.hour, date_utc.minute, date_utc.second)
        available_targets = [str(target) for target in eph.targets()]
        planet_map = {}
        for target in available_targets:
            for key, value in PLANET_MAPPINGS.items():
                if key in target:
                    planet_map[target] = value
                    break

        earth_key = next((k for k in available_targets if 'EARTH' in k), None)
        if not earth_key:
            raise ValueError("Earth not found")
        earth = eph[earth_key]

        results = []
        for target_key, name in planet_map.items():
            if target_key == earth_key: continue
            try:
                body = eph[target_key]
                astrometric = earth.at(t).observe(body)
                lon = astrometric.apparent().ecliptic_latlon()[1].degrees
                t2 = ts.utc((date_utc - timedelta(days=2)).year, (date_utc - timedelta(days=2)).month,
                            (date_utc - timedelta(days=2)).day, date_utc.hour, date_utc.minute, date_utc.second)
                lon2 = earth.at(t2).observe(body).apparent().ecliptic_latlon()[1].degrees
                is_retrograde = ((lon - lon2 + 360) % 360) > 180
                results.append({
                    "name": name,
                    "sign": get_zodiac_sign(lon),
                    "degree": round(lon % 30, 2),
                    "absolute_degree": round(lon, 2),
                    "retrograde": str(is_retrograde).lower(),
                    "house": get_house(lon)
                })
            except Exception as e:
                results.append({
                    "name": name, "sign": "Unknown", "degree": 0,
                    "absolute_degree": 0, "retrograde": "false", "house": 1,
                    "error": str(e)
                })
        return results
    except Exception as e:
        return []

@app.route("/natal-chart", methods=["POST"])
def natal_chart():
    try:
        data = request.json
        date, time = data.get("date"), data.get("time")
        lat, lon = float(data.get("lat")), float(data.get("lon"))
        tz_raw = data.get("tz", "+00:00")
        tz_hours = parse_timezone(tz_raw)
        dt_local = datetime.fromisoformat(f"{date}T{time}:00")
        dt_utc = dt_local - timedelta(hours=tz_hours)
        chart = calculate_chart(dt_utc)
        aspects = find_aspects(chart)
        return jsonify({
            "chart": chart,
            "aspects": aspects,
            "date": date, "time": time,
            "timezone": tz_raw,
            "location": {"lat": lat, "lon": lon}
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
    except: pass
    return None, None

def fetch_from_aztro(sign):
    try:
        url = f"https://aztro.sameerkumar.website/?sign={sign}&day=today"
        response = requests.post(url, timeout=5)
        if response.status_code == 200:
            data = response.json()
            return data.get("description"), "en"
    except: pass
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

        # If all sources failed, generate a fallback horoscope
        if not text:
            logging.warning("All horoscope sources failed, generating fallback")
            try:
                # Generate a horoscope with OpenAI as fallback
                response = client.chat.completions.create(
                    model="gpt-3.5-turbo",
                    messages=[
                        {"role": "system", "content": "You are an astrologer who writes brief daily horoscopes in Turkish."},
                        {"role": "user", "content": f"Write a short daily horoscope for {sign} in Turkish. Keep it positive and around 3-4 sentences."}
                    ]
                )
                text = response.choices[0].message.content
                lang = "tr"
            except Exception as e:
                logging.error(f"Fallback generation failed: {str(e)}")
                # Last resort fallback
                text = f"{sign.title()} burcu için bugün yeni başlangıçlar yapma ve kendini keşfetme zamanı. Enerjin yüksek, fırsatları değerlendir. Sevdiklerinle vakit geçirmek için güzel bir gün."
                lang = "tr"

        if lang == "tr":
            return jsonify({
                "sign": sign.title(),
                "original": text,
                "translated": text,
                "source": "fallback" if not any(source(sign)[0] for source in sources) else "api"
            })

        # Only translate if needed
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
            logging.error(f"Translation error: {str(e)}")
            # If translation fails, return original text
            translated = f"(Translation failed) {text}"

        return jsonify({
            "sign": sign.title(),
            "original": text,
            "translated": translated,
            "source": "api"
        })
    except Exception as e:
        logging.error(f"Error in translated-horoscope: {str(e)}")
        return jsonify({"error": f"Translation failed: {str(e)}"}), 500

@app.route("/health", methods=["GET"])
def health_check():
    return jsonify({
        "status": "ok",
        "timestamp": datetime.now().isoformat()
    })

if __name__ == "__main__":
    from waitress import serve
    port = int(os.environ.get("PORT", 5000))
    serve(app, host="0.0.0.0", port=port)
