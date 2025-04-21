from flask import Flask, request, jsonify
from openai import OpenAI
from skyfield.api import load, Topos, wgs84
from datetime import datetime, timedelta, timezone
import os
import requests
import math
import logging

# Set up logging
logging.basicConfig(level=logging.INFO, format='%(asctime)s - %(levelname)s - %(message)s')

app = Flask(__name__)
client = OpenAI(api_key=os.getenv("OPENAI_API_KEY"))

# Ephemeris files
EPHEMERIS_FILE = "de421.bsp"  # Changed to a more reliable ephemeris file
EPHEMERIS_URL = "https://naif.jpl.nasa.gov/pub/naif/generic_kernels/spk/planets/de421.bsp"

def download_ephemeris():
    if not os.path.exists(EPHEMERIS_FILE):
        try:
            logging.info(f"Downloading ephemeris file from {EPHEMERIS_URL}")
            import urllib.request
            urllib.request.urlretrieve(EPHEMERIS_URL, EPHEMERIS_FILE)
            logging.info(f"Successfully downloaded {EPHEMERIS_FILE}")
            return True
        except Exception as e:
            logging.error(f"Failed to download ephemeris file: {str(e)}")
            return False
    logging.info(f"Ephemeris file {EPHEMERIS_FILE} already exists")
    return True

# Try to download the ephemeris file
if not download_ephemeris():
    logging.error("Could not download ephemeris file. Using built-in ephemeris.")

PLANET_NAMES = {
    "sun": "Güneş", "moon": "Ay", "mercury": "Merkür", "venus": "Venüs", "mars": "Mars",
    "jupiter": "Jüpiter", "saturn": "Satürn", "uranus": "Uranüs", "neptune": "Neptün", "pluto": "Plüton"
}

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
        for j, p2 in enumerate(planets):
            if i >= j:
                continue
            diff = angle_difference(p1["degree"], p2["degree"])
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
        
        # Validate if date is within ephemeris range (add some safety margin)
        if dt_utc.year < 1850 or dt_utc.year > 2050:
            return jsonify({"error": f"Date {date} is outside valid range (1850-2050)"}), 400
        
        # Load timescale and ephemeris
        try:
            ts = load.timescale()
            t = ts.utc(dt_utc.year, dt_utc.month, dt_utc.day, 
                       dt_utc.hour, dt_utc.minute, dt_utc.second)
            
            # Try to load ephemeris file, fall back to built-in if needed
            try:
                eph = load(EPHEMERIS_FILE)
                logging.info(f"Successfully loaded ephemeris file {EPHEMERIS_FILE}")
            except Exception as eph_error:
                logging.warning(f"Error loading ephemeris file, falling back to built-in: {str(eph_error)}")
                eph = load('de421.bsp')  # Use a built-in ephemeris as fallback
            
            # Create observer location
            observer = wgs84.latlon(latitude_degrees=lat, longitude_degrees=lon)
            
            planet_keys = ["sun", "moon", "mercury", "venus", "mars", "jupiter", "saturn"]
            chart = []
            
            for key in planet_keys:
                try:
                    if key in eph:
                        body = eph[key]
                    else:
                        # Some ephemeris files name planets differently
                        alternative_names = {
                            "sun": "sun",
                            "moon": "moon",
                            "mercury": "mercury barycenter",
                            "venus": "venus barycenter",
                            "mars": "mars barycenter",
                            "jupiter": "jupiter barycenter",
                            "saturn": "saturn barycenter"
                        }
                        body = eph[alternative_names.get(key, key)]
                    
                    # Calculate position
                    astrometric = eph["earth"].at(t).observe(body).apparent()
                    lon_deg = astrometric.ecliptic_latlon()[1].degrees
                    
                    # Calculate retrograde status
                    prev_time = ts.utc((dt_utc - timedelta(days=1)).timetuple()[:6])
                    prev_astrometric = eph["earth"].at(prev_time).observe(body).apparent()
                    prev_lon = prev_astrometric.ecliptic_latlon()[1].degrees
                    
                    # Properly handle retrograde calculation
                    # A planet is retrograde if it appears to move backward in the sky
                    lon_diff = (lon_deg - prev_lon) % 360
                    if lon_diff > 180:
                        lon_diff -= 360
                    retro = lon_diff < 0
                    
                    chart.append({
                        "name": PLANET_NAMES[key],
                        "sign": get_zodiac_sign(lon_deg),
                        "degree": round(lon_deg % 30, 2),
                        "absolute_degree": round(lon_deg, 2),
                        "retrograde": retro,
                        "house": get_house(lon_deg)
                    })
                except Exception as planet_error:
                    logging.error(f"Error calculating position for {key}: {str(planet_error)}")
                    # Skip this planet if calculation fails
                    continue
            
            aspects = find_aspects(chart)
            
            return jsonify({
                "chart": chart,
                "aspects": aspects,
                "date": date,
                "time": time,
                "timezone": tz_raw,
                "location": {"lat": lat, "lon": lon}
            })
            
        except Exception as e:
            logging.error(f"Error in skyfield calculations: {str(e)}")
            return jsonify({"error": f"Calculation error: {str(e)}"}), 500
            
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
        "ephemeris_available": os.path.exists(EPHEMERIS_FILE),
        "timestamp": datetime.now().isoformat()
    })

if __name__ == "__main__":
    from waitress import serve
    port = int(os.environ.get("PORT", 5000))
    logging.info(f"Starting server on port {port}")
    serve(app, host="0.0.0.0", port=port)
