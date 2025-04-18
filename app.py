from flask import Flask, jsonify
import os
import requests
import openai

app = Flask(__name__)
openai.api_key = os.getenv("OPENAI_API_KEY")

# 1. Horoscope App API
def fetch_from_horoscope_app_api(sign):
    try:
        url = f"https://horoscope-app-api.vercel.app/api/v1/get-horoscope/daily?sign={sign}&day=today"
        response = requests.get(url, timeout=5)
        if response.status_code == 200:
            data = response.json()
            return data.get("data", {}).get("horoscope"), "en"
    except:
        return None, None

# 2. Aztro API (POST isteği gerekiyor)
def fetch_from_aztro_api(sign):
    try:
        url = f"https://aztro.sameerkumar.website/?sign={sign}&day=today"
        response = requests.post(url, timeout=5)
        if response.status_code == 200:
            data = response.json()
            return data.get("description"), "en"
    except:
        return None, None

# 3. Türkçe içerik: burc-yorumlari
def fetch_from_burc_yorumlari(sign):
    try:
        url = f"https://burc-yorumlari.vercel.app/get/{sign.lower()}"
        response = requests.get(url, timeout=5)
        if response.status_code == 200:
            data = response.json()
            return data.get("yorum"), "tr"
    except:
        return None, None

# Otomatik dil çevirisi (sadece İngilizce içerikler için)
def translate_to_turkish(text):
    try:
        chat_response = openai.ChatCompletion.create(
            model="gpt-3.5-turbo",
            messages=[
                {"role": "system", "content": "You are a helpful assistant who translates English astrology texts into Turkish."},
                {"role": "user", "content": f"Translate this horoscope to Turkish:\n\n{text}"}
            ]
        )
        return chat_response["choices"][0]["message"]["content"]
    except Exception as e:
        return f"[Çeviri hatası: {str(e)}]"

# Ana endpoint
@app.route("/translated-horoscope/<sign>", methods=["GET"])
def get_translated_horoscope(sign):
    sources = [
        fetch_from_horoscope_app_api,
        fetch_from_aztro_api,
        fetch_from_burc_yorumlari
    ]

    for source_func in sources:
        content, lang = source_func(sign)
        if content:
            break
    else:
        return jsonify({"error": "Tüm kaynaklar başarısız oldu."}), 500

    # İngilizce ise ChatGPT ile çevir
    if lang == "en":
        translated = translate_to_turkish(content)
    else:
        translated = content

    return jsonify({
        "sign": sign.title(),
        "original": content,
        "translated": translated,
        "source_language": lang
    })

if __name__ == "__main__":
    port = int(os.environ.get("PORT", 5000))
    app.run(host="0.0.0.0", port=port)
