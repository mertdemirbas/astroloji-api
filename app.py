from flask import Flask, request, jsonify
import os
import openai
import requests

app = Flask(__name__)
openai.api_key = os.getenv("OPENAI_API_KEY")

# 1. Horoscope App API (İngilizce)
def fetch_from_horoscope_app_api(sign):
    try:
        url = f"https://horoscope-app-api.vercel.app/api/v1/get-horoscope/daily?sign={sign}&day=today"
        response = requests.get(url, timeout=5)
        if response.status_code == 200:
            data = response.json()
            return data.get("data", {}).get("horoscope_data", ""), "en"
    except Exception as e:
        print("Horoscope App API error:", e)
    return None, None

# 2. Aztro API (İngilizce)
def fetch_from_aztro_api(sign):
    try:
        url = f"https://aztro.sameerkumar.website/?sign={sign}&day=today"
        response = requests.post(url, timeout=5)
        if response.status_code == 200:
            data = response.json()
            return data.get("description", ""), "en"
    except Exception as e:
        print("Aztro API error:", e)
    return None, None

# 3. Türkçe API
def fetch_from_burc_yorumlari(sign):
    try:
        turkish_map = {
            "aries": "koc", "taurus": "boga", "gemini": "ikizler", "cancer": "yengec",
            "leo": "aslan", "virgo": "basak", "libra": "terazi", "scorpio": "akrep",
            "sagittarius": "yay", "capricorn": "oglak", "aquarius": "kova", "pisces": "balik"
        }
        turkish_sign = turkish_map.get(sign.lower())
        if not turkish_sign:
            return None, None
        url = f"https://burc-yorumlari.vercel.app/get/{turkish_sign}"
        response = requests.get(url, timeout=5)
        if response.status_code == 200:
            data = response.json()
            if data and isinstance(data, list):
                return data[0].get("GunlukYorum", ""), "tr"
    except Exception as e:
        print("Burc Yorumlari API error:", e)
    return None, None

@app.route("/translated-horoscope/<sign>", methods=["GET"])
def get_translated_horoscope(sign):
    providers = [fetch_from_horoscope_app_api, fetch_from_aztro_api, fetch_from_burc_yorumlari]

    for provider in providers:
        english_text, lang = provider(sign)
        if english_text:
            if lang == "tr":
                return jsonify({
                    "sign": sign.title(),
                    "original": english_text,
                    "translated": english_text
                })

            try:
                translation = openai.ChatCompletion.create(
                    model="gpt-3.5-turbo",
                    messages=[
                        {"role": "system", "content": "You are a helpful assistant who translates astrology texts into Turkish."},
                        {"role": "user", "content": f"Translate this horoscope to Turkish:\n\n{english_text}"}
                    ]
                )
                translated = translation["choices"][0]["message"]["content"]
                return jsonify({
                    "sign": sign.title(),
                    "original": english_text,
                    "translated": translated
                })
            except Exception as e:
                return jsonify({"error": f"Translation failed: {str(e)}"}), 500

    return jsonify({"error": "No horoscope data returned from any provider."}), 400

if __name__ == "__main__":
    port = int(os.environ.get("PORT", 5000))
    app.run(host="0.0.0.0", port=port)
