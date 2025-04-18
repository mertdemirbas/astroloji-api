from flask import Flask, jsonify
import requests
import openai
import os

app = Flask(__name__)

# API keyleri environment'tan al
openai.api_key = os.getenv("OPENAI_API_KEY")
RAPID_API_KEY = os.getenv("RAPID_API_KEY")
RAPID_API_HOST = "best-daily-astrology-and-horoscope-api.p.rapidapi.com"

@app.route("/translated-horoscope/<sign>", methods=["GET"])
def get_translated_horoscope(sign):
    try:
        # 1. RapidAPI üzerinden İngilizce burç yorumu al
        url = f"https://{RAPID_API_HOST}/api/Detailed-Horoscope/"
        headers = {
            "X-RapidAPI-Key": RAPID_API_KEY,
            "X-RapidAPI-Host": RAPID_API_HOST
        }
        params = {"zodiacSign": sign.lower()}

        response = requests.get(url, headers=headers, params=params)
        data = response.json()

        english_text = data.get("prediction", "")

        if not english_text:
            return jsonify({"error": "No horoscope data returned"}), 400

        # 2. OpenAI ile Türkçeye çevir
        chat_response = openai.ChatCompletion.create(
            model="gpt-3.5-turbo",
            messages=[
                {"role": "system", "content": "You are a helpful assistant that translates astrology predictions from English to Turkish."},
                {"role": "user", "content": f"Translate this horoscope to Turkish:\n\n{english_text}"}
            ]
        )

        translated = chat_response["choices"][0]["message"]["content"]

        return jsonify({
            "sign": sign.title(),
            "english": english_text,
            "turkish": translated
        })

    except Exception as e:
        return jsonify({"error": str(e)}), 500


if __name__ == "__main__":
    port = int(os.environ.get("PORT", 5000))
    app.run(host="0.0.0.0", port=port)
