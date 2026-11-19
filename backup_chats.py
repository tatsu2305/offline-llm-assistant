# -*- coding: utf-8 -*-
"""
Kişisel Offline AI — Sohbet Geçmişi Yedekleme ve Geri Yükleme Aracı
Kullanım:
  py backup_chats.py                 -> Yeni tam yedek (.zip: SQLite DB + JSON + Markdown) oluşturur
  py backup_chats.py --list          -> Mevcut yedekleri listeler
  py backup_chats.py --restore DOSYA -> Belirtilen .zip yedeğinden veritabanını geri yükler
"""

import argparse
import sys
import zipfile
from pathlib import Path
from ai_manager import ChatDatabase, BACKUP_DIR, DB_PATH


def list_backups():
    backups = sorted(BACKUP_DIR.glob("chat_backup_*.zip"), reverse=True)
    if not backups:
        print("Henüz oluşturulmuş bir yedek bulunamadı.")
        return
    print(f"Toplam {len(backups)} yedek bulundu ({BACKUP_DIR}):")
    for b in backups:
        size_kb = round(b.stat().st_size / 1024.0, 2)
        print(f"  - {b.name} ({size_kb} KB)")


def restore_backup(zip_file: str):
    zp = Path(zip_file)
    if not zp.exists():
        zp = BACKUP_DIR / zip_file
    if not zp.exists():
        print(f"HATA: Yedek dosyası bulunamadı: {zip_file}")
        sys.exit(1)

    db = ChatDatabase()
    if DB_PATH.exists():
        pre_res = db.create_backup(tag="pre_restore_safety")
        print(f"Geri yükleme öncesi mevcut veritabanı güvenlik yedeği alındı: {pre_res['backup_path']}")

    with zipfile.ZipFile(zp, "r") as zf:
        if "chats.db" not in zf.namelist():
            print("HATA: Arşiv içinde 'chats.db' bulunamadı!")
            sys.exit(1)
        zf.extract("chats.db", path=DB_PATH.parent)

    restored_db = ChatDatabase()
    stats = restored_db.get_stats()
    print(f"BAŞARILI: Yedek geri yüklendi -> {DB_PATH}")
    print(f"Konuşma sayısı: {stats['conversations_count']} | Mesaj sayısı: {stats['messages_count']}")


def main():
    parser = argparse.ArgumentParser(description="Yerel AI Sohbet Geçmişi Yedekleme Aracı")
    parser.add_argument("--list", action="store_true", help="Mevcut yedekleri listele")
    parser.add_argument("--restore", type=str, help="Belirtilen yedek (.zip) dosyasını geri yükle")
    parser.add_argument("--tag", type=str, default="manual", help="Yedek dosya etiketi")
    args = parser.parse_args()

    if args.list:
        list_backups()
    elif args.restore:
        restore_backup(args.restore)
    else:
        db = ChatDatabase()
        info = db.create_backup(tag=args.tag)
        print("=== SOHBET GEÇMİŞİ YEDEKLENDİ ===")
        print(f"Yedek Dosyası : {info['backup_path']}")
        print(f"Konuşma Sayısı: {info['conversations_backed_up']}")
        print(f"Dosya Boyutu  : {info['size_kb']} KB")
        print("İçerik        : chats.db (SQLite) + chats_export.json + markdown/*.md")


if __name__ == "__main__":
    main()
