#!/bin/bash
echo "📦 Ephemeris dosyaları indiriliyor..."

# ephe klasörünü oluştur
mkdir -p ephe

# Dropbox zip dosyasını indir ve aç
curl -L "https://www.dropbox.com/scl/fo/xxvijpxf6q1p6t1u039dy/AJgLs_s1Xl77xRgFCtLfn6I?rlkey=kftsbgcaguihzfxmj8db5xsqn&dl=1" -o ephe.zip

# ZIP'i aç ve ephe klasörüne taşı
unzip ephe.zip -d ephe-temp
mv ephe-temp/* ephe/
rm -rf ephe-temp ephe.zip

echo "✅ Ephemeris verileri hazır, sunucu başlatılıyor..."
python app.py
