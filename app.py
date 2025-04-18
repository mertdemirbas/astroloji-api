from flask import Flask, jsonify
import os
import requests
from openai import OpenAI

app = Flask(__name__)
client = OpenAI(api_key=os.getenv("OPENAI_API_KEY"))

# 1. Horoscope App API
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

# 2. Aztro API (POST)
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
        # Kaynaklardan veri çek
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

        # İngilizce metni Türkçeye çevir
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

if __name__ == "__main__":
    port = int(os.environ.get("PORT", 5000))
    app.run(host="0.0.0.0", port=port)
