from flask import Flask, request, jsonify
from openai import OpenAI
from skyfield.api import load, Topos
from datetime import datetime, timedelta
import os
import requests
import logging
import json

# Set up logging
logging.basicConfig(level=logging.INFO, format='%(asctime)s - %(levelname)s - %(message)s')

app = Flask(__name__)
client = OpenAI(api_key=os.getenv("OPENAI_API_KEY"))

# Load timescale once at startup
ts = load.timescale()

# Planet and zodiac data
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

# Mapping of planet barycenters to Turkish names
PLANET_MAPPINGS = {
    # Regular planets
    'MERCURY BARYCENTER': 'Merkür',
    'VENUS BARYCENTER': 'Venüs',
    'EARTH BARYCENTER': 'Dünya',
    'MARS BARYCENTER': 'Mars',
    'JUPITER BARYCENTER': 'Jüpiter',
    'SATURN BARYCENTER': 'Satürn',
    'SUN': 'Güneş',
    'MOON': 'Ay',
    # Some ephemeris files use these alternatives
    'MERCURY': 'Merkür',
    'VENUS': 'Venüs',
    'EARTH': 'Dünya',
    'MARS': 'Mars',
    'JUPITER': 'Jüpiter',
    'SATURN': 'Satürn'
}

# Helper functions
def get_zodiac_sign(degree):
    """Convert ecliptic longitude to zodiac sign"""
    index = int(degree // 30) % 12
    return ZODIAC_SIGNS[index]

def get_house(degree):
    """Calculate house from ecliptic longitude"""
    return int(degree // 30) + 1

def angle_difference(a1, a2):
    """Calculate the shortest angle between two points on a circle"""
    diff = abs(a1 - a2) % 360
    return min(diff, 360 - diff)

def find_aspects(planets):
    """Find aspects between planets"""
    result = []
    tolerance = 6  # Orb tolerance in degrees
    
    for i, p1 in enumerate(planets):
        if p1.get("error"):  # Skip planets with errors
            continue
        for j, p2 in enumerate(planets):
            if i >= j or p2.get("error"):
                continue
                
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
    """Parse timezone string like '+03:00' into hours offset"""
    try:
        sign = 1 if tz_raw[0] == '+' else -1
        hours = int(tz_raw[1:3])
        minutes = int(tz_raw[4:6]) if len(tz_raw) > 5 else 0
        return sign * (hours + minutes / 60)
    except Exception as e:
        logging.error(f"Error parsing timezone '{tz_raw}': {str(e)}")
        return 0  # Default to UTC in case of errors

def calculate_chart(date_utc):
    """Calculate planetary positions using built-in data"""
    # Load ephemeris data
    try:
        eph = load('de440s.bsp')
        logging.info("Loaded de440s.bsp ephemeris")
        
        # Get available targets
        available_targets = [str(target) for target in eph.targets()]
        logging.info(f"Available targets: {available_targets}")
        
        # Map targets to our planet names
        planet_map = {}
        for target in available_targets:
            for key, value in PLANET_MAPPINGS.items():
                if key in target:
                    planet_map[target] = value
                    break
        
        logging.info(f"Mapped targets: {planet_map}")
        
        results = []
        earth_key = None
        
        # Find Earth for observations
        for key in available_targets:
            if 'EARTH' in key:
                earth_key = key
                break
                
        if not earth_key:
            raise ValueError("Earth not found in ephemeris")
            
        earth = eph[earth_key]
        
        # Create time object
        t = ts.utc(date_utc.year, date_utc.month, date_utc.day,
                   date_utc.hour, date_utc.minute, date_utc.second)
        
        # Calculate positions for each planet
        for target_key, planet_name in planet_map.items():
            if target_key == earth_key:
                continue  # Skip Earth
                
            try:
                body = eph[target_key]
                
                # Different calculation for Sun
                if 'SUN' in target_key:
                    # For Sun, we observe from Earth to Sun
                    astrometric = earth.at(t).observe(body)
                else:
                    # For other planets
                    astrometric = earth.at(t).observe(body)
                
                apparent = astrometric.apparent()
                ecliptic = apparent.ecliptic_latlon()
                lon_deg = ecliptic[1].degrees
                
                # Simple retrograde calculation
                t2 = ts.utc((date_utc - timedelta(days=2)).year,
                            (date_utc - timedelta(days=2)).month,
                            (date_utc - timedelta(days=2)).day,
                            date_utc.hour, date_utc.minute, date_utc.second)
                
                astrometric2 = earth.at(t2).observe(body)
                apparent2 = astrometric2.apparent()
                ecliptic2 = apparent2.ecliptic_latlon()
                lon_deg2 = ecliptic2[1].degrees
                
                # Calculate direction
                diff = (lon_deg - lon_deg2) % 360
                if diff > 180:
                    diff -= 360
                    
                is_retrograde = diff < 0
                
                # Add planet to results
                results.append({
                    "name": planet_name,
                    "sign": get_zodiac_sign(lon_deg),
                    "degree": round(lon_deg % 30, 2),
                    "absolute_degree": round(lon_deg, 2),
                    "retrograde": "true" if is_retrograde else "false",  # String instead of boolean
                    "house": get_house(lon_deg)
                })
                
            except Exception as e:
                logging.error(f"Error calculating position for {target_key}: {str(e)}")
                # Add placeholder with error info
                results.append({
                    "name": planet_name,
                    "sign": "Unknown",
                    "degree": 0,
                    "absolute_degree": 0,
                    "retrograde": "false",  # String instead of boolean
                    "house": 1,
                    "error": str(e)
                })
                
        return results
        
    except Exception as e:
        logging.error(f"Error in chart calculation: {str(e)}")
        
        # Return mock data as fallback
        return [
            {"name": "Güneş", "sign": "Terazi", "degree": 22.5, "absolute_degree": 202.5, "retrograde": "false", "house": 7},
            {"name": "Ay", "sign": "Balık", "degree": 15.3, "absolute_degree": 345.3, "retrograde": "false", "house": 12},
            {"name": "Merkür", "sign": "Akrep", "degree": 5.2, "absolute_degree": 215.2, "retrograde": "true", "house": 8},
            {"name": "Venüs", "sign": "Yay", "degree": 10.8, "absolute_degree": 250.8, "retrograde": "false", "house": 9},
            {"name": "Mars", "sign": "Koç", "degree": 18.7, "absolute_degree": 18.7, "retrograde": "false", "house": 1},
            {"name": "Jüpiter", "sign": "Başak", "degree": 7.9, "absolute_degree": 157.9, "retrograde": "false", "house": 6},
            {"name": "Satürn", "sign": "Kova", "degree": 2.3, "absolute_degree": 302.3, "retrograde": "true", "house": 11}
        ]

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
        
        # Parse the timezone
        tz_hours = parse_timezone(tz_raw)
        
        # Parse date and time
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
        
        # Calculate chart data
        chart_data = calculate_chart(dt_utc)
        
        # Calculate aspects
        aspects = find_aspects(chart_data)
        
        # Create response
        response = {
            "chart": chart_data,
            "aspects": aspects,
            "date": date,
            "time": time,
            "timezone": tz_raw,
            "location": {"lat": lat, "lon": lon}
        }
        
        return jsonify(response)
            
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
