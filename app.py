from flask import Flask, jsonify
import os
import requests
from openai import OpenAI

app = Flask(__name__)
client = OpenAI(api_key=os.getenv("OPENAI_API_KEY"))

def fetch_from_horoscope_app_api(sign):
    """İlk deneme: İngilizce günlük burç."""
    url = f"https://horoscope-app-api.vercel.app/api/v1/get-horoscope/daily?sign={sign}&day=today"
    resp = requests.get(url, timeout=5)
    if resp.status_code == 200:
        data = resp.json()
        text = data.get("data", {}).get("horoscope_data")
        if text:
            return text, "en"
    return None, None

def fetch_from_aztro_api(sign):
    """İkinci deneme: İngilizce Aztro API (POST)."""
    url = f"https://aztro.sameerkumar.website/?sign={sign}&day=today"
    resp = requests.post(url, timeout=5)
    if resp.status_code == 200:
        data = resp.json()
        text = data.get("description")
        if text:
            return text, "en"
    return None, None

def fetch_from_burc_yorumlari(sign):
    """Son çare: Türkçe kaynaktan."""
    url = f"https://burc-yorumlari.vercel.app/get/{sign.lower()}"
    resp = requests.get(url, timeout=5)
    if resp.status_code == 200:
        data = resp.json()
        if isinstance(data, list) and data:
            text = data[0].get("GunlukYorum")
            if text:
                return text, "tr"
    return None, None

@app.route("/translated-horoscope/<sign>", methods=["GET"])
def get_translated_horoscope(sign):
    sign = sign.lower()
    # 1) İngilizce Kaynak A
    text, lang = fetch_from_horoscope_app_api(sign)
    # 2) Eğer yoksa İngilizce Kaynak B
    if not text:
        text, lang = fetch_from_aztro_api(sign)
    # 3) Eğer hala yoksa Türkçe Kaynak
    if not text:
        text, lang = fetch_from_burc_yorumlari(sign)

    if not text:
        return jsonify({"error": "No horoscope data available."}), 400

    # Eğer zaten Türkçe geldiyse birebir dön
    if lang == "tr":
        return jsonify({
            "sign": sign.title(),
            "original": text,
            "translated": text
        })

    # İngilizce kaynağı Türkçeye çevir
    try:
        completion = client.chat.completions.create(
            model="gpt-3.5-turbo",
            messages=[
                {"role": "system", "content": "You are a helpful assistant translating astrology texts into Turkish."},
                {"role": "user",   "content": f"Translate this horoscope into Turkish:\n\n{text}"}
            ]
        )
        translated = completion.choices[0].message.content.strip()
    except Exception as e:
        # Eğer çeviri başarısızsa, özgün İngilizceyi geri ver
        translated = f"(Çeviri yapılamadı) {text}"

    return jsonify({
        "sign": sign.title(),
        "original": text,
        "translated": translated
    })

if __name__ == "__main__":
    port = int(os.environ.get("PORT", 5000))
    app.run(host="0.0.0.0", port=port)
