# -*- coding: utf-8 -*-
"""
Kişisel Offline AI Sistemi — Kapsamlı Doğrulama ve Test Betiği
1. Masaüstü kısayolunu oluşturur.
2. Türkçe, Genel Bilgi, Mantık Yürütme ve Günlük Sohbet testlerini çalıştırır ve chats.db'ye kaydeder.
3. RX 7600 GPU (ROCm) hızlandırmasını, VRAM ve RAM tüketimini ölçer.
4. Ağ bağlantılarını (Get-NetTCPConnection) kontrol ederek 127.0.0.1 dışında hiçbir dış bağlantı olmadığını kanıtlar.
5. Yedekleme sistemini test eder.
6. Hem Pencere X Butonu (--test-x-close) hem de Sistem Tepsisi Quit/Exit (--test-tray-quit) kapatma davranışlarını ayrı ayrı test eder.
"""

import json
import subprocess
import sys
import time
from pathlib import Path

from ai_manager import (
    BASE_DIR,
    ChatDatabase,
    OllamaLifecycleManager,
    DEFAULT_MODEL,
    LIFECYCLE_LOG_PATH,
    SHUTDOWN_ERROR_LOG_PATH,
    get_ollama_processes_memory_mb,
)


def create_desktop_shortcut():
    app_script = str(BASE_DIR / "app.py")
    work_dir = str(BASE_DIR)
    pythonw_exe = str(Path(sys.executable).with_name("pythonw.exe"))
    if not Path(pythonw_exe).exists():
        pythonw_exe = sys.executable

    ps_script = f"""
    $WshShell = New-Object -ComObject WScript.Shell
    $DesktopPath = [Environment]::GetFolderPath("Desktop")
    $Shortcut = $WshShell.CreateShortcut("$DesktopPath\\Kişisel Offline AI.lnk")
    $Shortcut.TargetPath = "{pythonw_exe}"
    $Shortcut.Arguments = '"{app_script}"'
    $Shortcut.WorkingDirectory = "{work_dir}"
    $Shortcut.IconLocation = "$env:LOCALAPPDATA\\Programs\\Ollama\\app.ico"
    $Shortcut.Description = "Kişisel Offline AI Sohbet Sistemi (Qwen - Yerel)"
    $Shortcut.Save()
    """
    subprocess.run(["powershell", "-NoProfile", "-Command", ps_script], check=True)
    print("[OK] Masaüstü kısayolu oluşturuldu: Kişisel Offline AI.lnk")


def check_network_isolation() -> dict:
    """Ollama süreçlerinin tüm TCP bağlantılarını denetler."""
    ps_cmd = r"""
    $procs = Get-Process *ollama* -ErrorAction SilentlyContinue
    if (-not $procs) { Write-Output "[]"; exit }
    $pids = $procs.Id
    $conns = Get-NetTCPConnection -ErrorAction SilentlyContinue | Where-Object { $pids -contains $_.OwningProcess }
    $conns | Select-Object LocalAddress, LocalPort, RemoteAddress, RemotePort, State, OwningProcess | ConvertTo-Json -Compress
    """
    res = subprocess.run(["powershell", "-NoProfile", "-Command", ps_cmd], capture_output=True, text=True)
    out = res.stdout.strip()
    if not out:
        return {"connections": [], "external_connections": []}
    conns = json.loads(out)
    if isinstance(conns, dict):
        conns = [conns]
    external = [
        c for c in conns
        if c.get("RemoteAddress") not in ("0.0.0.0", "127.0.0.1", "::", "::1", None)
    ]
    return {"connections": conns, "external_connections": external}


def main():
    create_desktop_shortcut()

    db = ChatDatabase()
    mgr = OllamaLifecycleManager(db)

    print("\n--- 1. OLLAMA SERVİSİ BAŞLATILIYOR (127.0.0.1:11434) ---")
    mgr.start_ollama(preload_model=False)

    conv = db.create_conversation(title="Kurulum Doğrulama ve Kalite Testleri (Türkçe / Mantık / Genel Bilgi)")
    conv_id = conv["id"]

    test_cases = [
        (
            "Türkçe Dil ve Anlatım Testi",
            "Merhaba! Bana yapay zeka modellerinin yerel bilgisayarda (offline) çalışmasının gizlilik açısından sağladığı 3 temel avantajı akıcı ve düzgün bir Türkçeyle kısaca açıklar mısın?",
        ),
        (
            "Genel Bilgi Testi",
            "Türkiye'nin coğrafi bölgelerini sayıp Karadeniz Bölgesi'nin iklim ve bitki örtüsü özelliklerini 2-3 cümleyle özetler misin?",
        ),
        (
            "Mantık Yürütme Testi",
            "Ayşe, Burak'tan uzundur. Ceren ise Ayşe'den kısadır ama Burak'tan uzundur. Bu üç kişiyi uzundan kısaya doğru sıralar mısın? Sonucu adım adım açıkla.",
        ),
        (
            "Günlük Sohbet Testi",
            "Bugün evde odaklanarak çalışmam gereken yoğun bir gün. Sabah kahvesinden sonra dikkatimi dağıtmadan çalışabilmek için bana samimi ve uygulanabilir 3 küçük tavsiye verir misin?",
        ),
    ]

    results = []
    for category, prompt in test_cases:
        print(f"\n[TEST] {category}")
        print(f"Soru: {prompt}")
        reply_chunks = []
        done_metrics = {}
        for evt in mgr.stream_chat(conv_id, prompt):
            if evt["type"] == "chunk":
                reply_chunks.append(evt["content"])
            elif evt["type"] == "done":
                done_metrics = evt.get("metrics", {})
        full_reply = "".join(reply_chunks).strip()
        print(f"Yanıt: {full_reply}")
        print(f"Metrikler: {done_metrics}")
        results.append({"category": category, "prompt": prompt, "reply": full_reply, "metrics": done_metrics})

    print("\n--- 2. GPU / VRAM / RAM VE AĞ İZOLASYONU DOĞRULAMASI ---")
    status_loaded = mgr.get_status()
    net_check = check_network_isolation()
    print("Yüklü Model Durumu:", json.dumps(status_loaded, ensure_ascii=False, indent=2))
    print("Ağ Bağlantı Denetimi:", json.dumps(net_check, ensure_ascii=False, indent=2))

    print("\n--- 3. YEDEKLEME TESTİ ---")
    backup_info = db.create_backup(tag="kurulum_testi")
    print("Yedekleme Sonucu:", json.dumps(backup_info, ensure_ascii=False, indent=2))

    # Önce mevcut servisi temizce kapat ki masaüstü uygulaması kendi yaşam döngüsünü test etsin
    mgr.execute_ordered_shutdown(trigger_source="VERIFY_SCRIPT_CLEANUP")
    time.sleep(1.5)

    print("\n--- 4. OTOMATİK KAPATMA TESTİ A: PENCERE SAĞ ÜST 'X' BUTONU (--test-x-close) ---")
    proc_x = subprocess.run(
        [sys.executable, str(BASE_DIR / "app.py"), "--test-x-close"],
        capture_output=True,
        text=True,
        timeout=90,
    )
    after_x_procs = get_ollama_processes_memory_mb()
    print(f"X Butonu Kapatma Testi Çıkış Kodu: {proc_x.returncode} | Kalan Ollama Süreci: {after_x_procs['count']}")

    time.sleep(1.5)

    print("\n--- 5. OTOMATİK KAPATMA TESTİ B: SİSTEM TEPSİSİ 'Quit / Exit' (--test-tray-quit) ---")
    proc_tray = subprocess.run(
        [sys.executable, str(BASE_DIR / "app.py"), "--test-tray-quit"],
        capture_output=True,
        text=True,
        timeout=90,
    )
    after_tray_procs = get_ollama_processes_memory_mb()
    print(f"Sistem Tepsisi Quit Testi Çıkış Kodu: {proc_tray.returncode} | Kalan Ollama Süreci: {after_tray_procs['count']}")

    print("\n--- 6. VERİTABANI KORUMA VE LOG KONTROLÜ ---")
    final_stats = db.get_stats()
    print("Final Veritabanı İstatistikleri:", json.dumps(final_stats, ensure_ascii=False, indent=2))
    print(f"Hata Kaydı Dosyası Mevcut mu?: {SHUTDOWN_ERROR_LOG_PATH.exists()}")


if __name__ == "__main__":
    main()
