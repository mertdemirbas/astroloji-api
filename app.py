from flask import Flask, request, jsonify
from openai import OpenAI
from skyfield.api import load, Topos, Star, wgs84
from datetime import datetime, timedelta, timezone
import os
import requests
import math
import logging

# Set up logging
logging.basicConfig(level=logging.INFO, format='%(asctime)s - %(levelname)s - %(message)s')

app = Flask(__name__)
client = OpenAI(api_key=os.getenv("OPENAI_API_KEY"))

# Load timescale once at startup
ts = load.timescale()

# Planetary ephemeris calculations without relying on external files
def calculate_planetary_positions(date_utc):
    """Calculate planetary positions using built-in data"""
    planets = load('de440s.bsp')  # Use the bundled ephemeris
    earth = planets['earth']
    
    # Dictionary to track planetary positions
    results = []

    # Date for calculation
    t = ts.utc(date_utc.year, date_utc.month, date_utc.day, 
                date_utc.hour, date_utc.minute, date_utc.second)
    
    # Calculate position for each planet
    planet_list = {
        'sun': 'Güneş',
        'moon': 'Ay',
        'mercury': 'Merkür', 
        'venus': 'Venüs', 
        'mars': 'Mars',
        'jupiter barycenter': 'Jüpiter', 
        'saturn barycenter': 'Satürn'
    }
    
    # Get planet positions
    for key, name in planet_list.items():
        try:
            planet = planets[key]
            astrometric = earth.at(t).observe(planet)
            apparent = astrometric.apparent()
            ecliptic = apparent.ecliptic_latlon()
            lon_deg = ecliptic[1].degrees
            
            # Calculate retrograde (simplified)
            t2 = ts.utc((date_utc - timedelta(days=2)).year, 
                         (date_utc - timedelta(days=2)).month, 
                         (date_utc - timedelta(days=2)).day,
                         date_utc.hour, date_utc.minute, date_utc.second)
            
            astrometric2 = earth.at(t2).observe(planet)
            apparent2 = astrometric2.apparent()
            ecliptic2 = apparent2.ecliptic_latlon()
            lon_deg2 = ecliptic2[1].degrees
            
            # Calculate retrograde
            diff = (lon_deg - lon_deg2) % 360
            if diff > 180:
                diff -= 360
            retro = diff < 0
            
            results.append({
                "name": name,
                "sign": get_zodiac_sign(lon_deg),
                "degree": round(lon_deg % 30, 2),
                "absolute_degree": round(lon_deg, 2),
                "retrograde": retro,
                "house": get_house(lon_deg)
            })
        except Exception as e:
            logging.error(f"Error calculating position for {key}: {str(e)}")
            # Add placeholder data
            results.append({
                "name": name,
                "sign": "Unknown",
                "degree": 0,
                "absolute_degree": 0,
                "retrograde": False,
                "house": 1,
                "error": str(e)
            })
    
    return results

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
        if "error" in p1:  # Skip planets with errors
            continue
        for j, p2 in enumerate(planets):
            if i >= j or "error" in p2:
                continue
            diff = angle_difference(p1["absolute_degree"], p2["absolute_degree"])
            for name, target in ASPECTS.items():
                if abs(diff - target) <= tolerance:
                    result.append({
                        "between": f'{p1["name"]} & {p2["name"]}',
                        "aspect": name,
                        "orb": round(abs(diff - target), 2)
                    })
    return result

def parse_timezone(tz_raw):
    """Parse timezone string like '+03:00' into hours offset"""
    try:
        sign = 1 if tz_raw[0] == '+' else -1
        hours = int(tz_raw[1:3])
        minutes = int(tz_raw[4:6]) if len(tz_raw) > 5 else 0
        return sign * (hours + minutes / 60)
    except Exception as e:
        logging.error(f"Error parsing timezone '{tz_raw}': {str(e)}")
        return 0  # Default to UTC in case of errors

@app.route("/natal-chart", methods=["POST"])
def natal_chart():
    try:
        data = request.json
        date = data.get("date")       # Örn: "1994-09-15"
        time = data.get("time")       # Örn: "15:30"
        lat = float(data.get("lat"))  # Örn: 41.0082
        lon = float(data.get("lon"))  # Örn: 28.9784
        tz_raw = data.get("tz", "+00:00")
        
        logging.info(f"Request received for date={date}, time={time}, lat={lat}, lon={lon}, tz={tz_raw}")
        
        # Parse the timezone more robustly
        tz_hours = parse_timezone(tz_raw)
        
        # Parse date and time with better error handling
        try:
            dt_local = datetime.fromisoformat(f"{date}T{time}:00")
        except ValueError:
            # Try alternate parsing if the first method fails
            try:
                date_parts = date.split("-")
                time_parts = time.split(":")
                dt_local = datetime(
                    year=int(date_parts[0]), 
                    month=int(date_parts[1]), 
                    day=int(date_parts[2]),
                    hour=int(time_parts[0]),
                    minute=int(time_parts[1])
                )
            except Exception as e:
                return jsonify({"error": f"Invalid date or time format: {str(e)}"}), 400
        
        # Convert local time to UTC
        dt_utc = dt_local - timedelta(hours=tz_hours)
        
        logging.info(f"Converted to UTC: {dt_utc}")
        
        # Calculate the chart using our safer method
        chart_data = calculate_planetary_positions(dt_utc)
        
        # Calculate aspects
        aspects = find_aspects(chart_data)
        
        return jsonify({
            "chart": chart_data,
            "aspects": aspects,
            "date": date,
            "time": time,
            "timezone": tz_raw,
            "location": {"lat": lat, "lon": lon}
        })
            
    except Exception as e:
        logging.error(f"General error in natal_chart: {str(e)}")
        return jsonify({"error": str(e)}), 400

# Günlük burç yorumları
def fetch_from_burc_yorumlari(sign):
    try:
        url = f"https://burc-yorumlari.vercel.app/get/{sign.lower()}"
        logging.info(f"Fetching horoscope from {url}")
        response = requests.get(url, timeout=5)
        if response.status_code == 200:
            data = response.json()
            if isinstance(data, list) and data:
                return data[0].get("GunlukYorum"), "tr"
        logging.warning(f"Failed to get data from burc-yorumlari, status: {response.status_code}")
    except Exception as e:
        logging.error(f"Error fetching from burc-yorumlari: {str(e)}")
    return None, None

def fetch_from_aztro(sign):
    try:
        url = f"https://aztro.sameerkumar.website/?sign={sign}&day=today"
        logging.info(f"Fetching horoscope from {url}")
        response = requests.post(url, timeout=5)
        if response.status_code == 200:
            data = response.json()
            return data.get("description"), "en"
        logging.warning(f"Failed to get data from aztro, status: {response.status_code}")
    except Exception as e:
        logging.error(f"Error fetching from aztro: {str(e)}")
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
            "translated": translated
        })
    except Exception as e:
        logging.error(f"Error in translated-horoscope: {str(e)}")
        return jsonify({"error": f"Translation failed: {str(e)}"}), 500

@app.route("/health", methods=["GET"])
def health_check():
    """Health check endpoint to verify the API is running properly"""
    return jsonify({
        "status": "ok",
        "timestamp": datetime.now().isoformat()
    })

if __name__ == "__main__":
    from waitress import serve
    port = int(os.environ.get("PORT", 5000))
    logging.info(f"Starting server on port {port}")
    serve(app, host="0.0.0.0", port=port)
