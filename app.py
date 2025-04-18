from flask import Flask, jsonify
import os
import requests
import openai

app = Flask(__name__)

# OpenAI API Key (Render ortam değişkeninden alınır)
openai.api_key = os.getenv("OPENAI_API_KEY")

# 1. https://horoscope-app-api.vercel.app/ (EN)
def fetch_from_horoscope_app_api(sign):
    try:
        url = f"https://horoscope-app-api.vercel.app/api/v1/get-horoscope/daily?sign={sign}&day=today"
        response = requests.get(url, timeout=5)
        if response.status_code == 200:
            data = response.json()
            return data.get("data", {}).get("horoscope"), "en"
    except:
        pass
    return None, None

# 2. https://aztro.sameerkumar.website/ (EN)
def fetch_from_aztro_api(sign):
    try:
        url = f"https://aztro.sameerkumar.website/?sign={sign}&day=today"
        response = requests.post(url, timeout=5)
        if response.status_code == 200:
            data = response.json()
            return data.get("description"), "en"
    except:
        pass
    return None, None

# 3. https://burc-yorumlari.vercel.app/ (TR)
def fetch_from_burc_yorumlari(sign):
    try:
        url = f"https://burc-yorumlari.vercel.app/api/{sign.lower()}"
        response = requests.get(url, timeout=5)
        if response.status_code == 200:
            data = response.json()
            return data.get("yorum"), "tr"
    except:
        pass
    return None, None

@app.route("/translated-horoscope/<sign>", methods=["GET"])
def get_translated_horoscope(sign):
    try:
        # Üç API'yi sırayla dene
        for fetch_func in [fetch_from_horoscope_app_api, fetch_from_aztro_api, fetch_from_burc_yorumlari]:
            text, lang = fetch_func(sign)
            if text:
                break
        else:
            return jsonify({"error": "No horoscope data returned from any provider."}), 400

        # İngilizce ise çevir, Türkçe ise olduğu gibi gönder
        if lang == "en":
            chat_response = openai.ChatCompletion.create(
                model="gpt-3.5-turbo",
                messages=[
                    {"role": "system", "content": "You are a helpful assistant who translates astrology texts into Turkish."},
                    {"role": "user", "content": f"Translate this horoscope to Turkish:\n\n{text}"}
                ]
            )
            translated = chat_response["choices"][0]["message"]["content"]
        else:
            translated = text

        return jsonify({
            "sign": sign.title(),
            "original": text,
            "translated": translated
        })

    except Exception as e:
        return jsonify({"error": str(e)}), 500

if __name__ == "__main__":
    port = int(os.environ.get("PORT", 5000))
    app.run(host="0.0.0.0", port=port)
