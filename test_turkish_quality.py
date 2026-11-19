# -*- coding: utf-8 -*-
"""
Kişisel Offline AI — Türkçe Cevap Kalitesi ve Sistem Talimatları Doğrulama Testi
Model: qwen3:8b (Değiştirilmedi)
"""

import json
from ai_manager import ChatDatabase, OllamaLifecycleManager, DEFAULT_MODEL, DEFAULT_SYSTEM_PROMPT


def ask_single(mgr: OllamaLifecycleManager, db: ChatDatabase, conv_id: str, question: str) -> tuple[str, dict]:
    chunks = []
    metrics = {}
    for evt in mgr.stream_chat(conv_id, question):
        if evt["type"] == "chunk":
            chunks.append(evt["content"])
        elif evt["type"] == "done":
            metrics = evt.get("metrics", {})
    return "".join(chunks).strip(), metrics


def main():
    db = ChatDatabase()
    mgr = OllamaLifecycleManager(db)

    print(f"Aktif Model: {mgr.model_name} (Beklenen: {DEFAULT_MODEL})")
    mgr.start_ollama(preload_model=False)

    # 1. Özel zorunlu test sorusu
    conv_main = db.create_conversation(title="Türkçe Cevap Kalitesi Doğrulama Testleri (Qwen3 8B)")
    cid = conv_main["id"]

    target_q = "Bir konuda emin değilsen nasıl cevap vermelisin?"
    expected_a = "Emin olmadığım konularda kesin konuşmam. Bilgimden emin değilsem bunu açıkça söylerim ve tahminlerimi gerçek bilgi gibi sunmam."

    print("\n" + "=" * 70)
    print("[ÖZEL TEST SORUSU]")
    print(f"Soru    : {target_q}")
    ans0, met0 = ask_single(mgr, db, cid, target_q)
    print(f"Cevap   : {ans0}")
    print(f"Beklenen: {expected_a}")
    print(f"Birebir Eşleşme: {ans0.strip('\"') == expected_a}")
    print(f"Metrik  : {met0}")

    # 2. 5 farklı Türkçe soru ile kalite testi
    five_questions = [
        (
            "1. Basit ve Doğrudan Bilgi Sorusu (Kısa/Net Cevap Testi)",
            "Türkiye'nin başkenti neresidir ve hangi coğrafi bölgede yer alır?",
        ),
        (
            "2. Bilinemeyecek / Emin Olunmayan Bilgi Sorusu (Uydurmama Testi)",
            "14 Kasım 2034 tarihinde Ankara'da düzenlenecek yapay zeka zirvesinin açılış konuşmasını kim yapacak?",
        ),
        (
            "3. Eksik / Belirsiz Soru (Tahmin Yürütmeyip Açıklama İsteme Testi)",
            "Bunu nasıl daha hızlı çalıştırabilirim?",
        ),
        (
            "4. Teknik Soru (Kısa Örnek Verip Konudan Uzaklaşmama Testi)",
            "Python'da bir listedeki tekrar eden elemanları en kısa nasıl kaldırırım?",
        ),
        (
            "5. Günlük Sohbet (Doğal, Samimi ve Tekrarsız Türkçe Testi)",
            "Akşam yemeğinden sonra üstüme bir ağırlık çöktü ama bu akşam bitirmem gereken kısa bir işim var. Ne yapmamı önerirsin?",
        ),
    ]

    for label, q in five_questions:
        conv_q = db.create_conversation(title=f"Kalite Testi: {label.split('(')[0].strip()}")
        print("\n" + "-" * 70)
        print(f"[{label}]")
        print(f"Soru  : {q}")
        ans, met = ask_single(mgr, db, conv_q["id"], q)
        print(f"Cevap : {ans}")
        print(f"Metrik: {met}")

    print("\n" + "=" * 70)
    print("Test tamamlandı, Ollama güvenli kapatma prosedürü çalıştırılıyor...")
    shutdown_res = mgr.execute_ordered_shutdown(trigger_source="QUALITY_TEST_COMPLETE")
    print("Kapatma Özeti:", json.dumps(shutdown_res, ensure_ascii=False))


if __name__ == "__main__":
    main()
