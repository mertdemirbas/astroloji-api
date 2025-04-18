import openai  # eğer yukarıda yoksa

# OpenAI API key’in
openai.api_key = "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"

# RapidAPI bilgilerin
RAPID_API_KEY = "83994d9cc9msh8404adef81063ffp1f7f85jsnef6d3304c8dd"
RAPID_API_HOST = "best-daily-astrology-and-horoscope-api.p.rapidapi.com"

@app.route("/translated-horoscope/<sign>", methods=["GET"])
def get_translated_horoscope(sign):
    try:
        # 1. RapidAPI'den İngilizce yorum al
        url = "https://best-daily-astrology-and-horoscope-api.p.rapidapi.com/api/Detailed-Horoscope/"
        params = {"zodiacSign": sign.lower()}
        headers = {
            "X-RapidAPI-Key": RAPID_API_KEY,
            "X-RapidAPI-Host": RAPID_API_HOST
        }

        response = requests.get(url, headers=headers, params=params)
        data = response.json()
        english_text = data.get("horoscope", "")

        if not english_text:
            return jsonify({"error": "No horoscope data returned"}), 400

        # 2. OpenAI ile Türkçeye çevir
        chat_response = openai.ChatCompletion.create(
            model="gpt-3.5-turbo",
            messages=[
                {"role": "system", "content": "You are a helpful assistant who translates astrology texts into Turkish."},
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
