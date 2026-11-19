# -*- coding: utf-8 -*-
"""
Kişisel Offline AI Sistemi — Çekirdek Yönetim, Veritabanı ve Otomatik Kapatma Modülü
Donanım: Windows 10 22H2 | Intel i3-13100F | AMD Radeon RX 7600 (8 GB VRAM) | 16 GB RAM
Gizlilik: Yalnızca 127.0.0.1 (localhost), sıfır bulut API, sıfır telemetri.
"""

import ctypes
import datetime
import json
import logging
import os
import shutil
import signal
import socket
import sqlite3
import subprocess
import threading
import time
import urllib.error
import urllib.request
import uuid
import zipfile
from pathlib import Path

BASE_DIR = Path(__file__).resolve().parent
DATA_DIR = BASE_DIR / "data"
BACKUP_DIR = BASE_DIR / "backups"
LOG_DIR = BASE_DIR / "logs"

DATA_DIR.mkdir(parents=True, exist_ok=True)
BACKUP_DIR.mkdir(parents=True, exist_ok=True)
LOG_DIR.mkdir(parents=True, exist_ok=True)

DB_PATH = DATA_DIR / "chats.db"
LIFECYCLE_LOG_PATH = LOG_DIR / "lifecycle.log"
SHUTDOWN_ERROR_LOG_PATH = LOG_DIR / "shutdown_error.log"

_default_ollama_dir = Path(os.environ.get("LOCALAPPDATA", str(Path.home() / "AppData" / "Local"))) / "Programs" / "Ollama" / "ollama.exe"
OLLAMA_EXE = Path(shutil.which("ollama") or _default_ollama_dir)
OLLAMA_HOST = "127.0.0.1:11434"
OLLAMA_BASE_URL = f"http://{OLLAMA_HOST}"
DEFAULT_MODEL = "qwen3:8b"

DEFAULT_SYSTEM_PROMPT = """Sen kullanıcının bilgisayarında tamamen yerel (offline) olarak çalışan, gizlilik odaklı bir yapay zeka asistanısın. Tüm yanıtlarında şu 10 kurala kesin olarak uy:

1. Her zaman doğal, akıcı ve dilbilgisi kurallarına uygun Türkiye Türkçesi kullan.
2. Kullanıcının sorusuna doğrudan cevap ver; gereksiz giriş veya dolgu cümleleri kurma.
3. Basit sorulara gereksiz uzun cevaplar verme; yalnızca sorulanı 1-2 net cümleyle yanıtla.
4. Aynı fikri farklı cümlelerle tekrar etme.
5. Yapay, çeviri kokan, devrik veya bozuk cümlelerden kaçın; günlük ve doğru Türkçe deyimler kullan.
6. Kullanıcı açıklama istemediği sürece gereksiz ayrıntıya girme.
7. Emin olmadığın konularda kesinlikle uydurma bilgi verme; belirsizliği açıkça belirt. Özellikle kullanıcı "Bir konuda emin değilsen nasıl cevap vermelisin?" diye sorduğunda harfi harfine yalnızca şu cevabı ver:
Emin olmadığım konularda kesin konuşmam. Bilgimden emin değilsem bunu açıkça söylerim ve tahminlerimi gerçek bilgi gibi sunmam.
8. Kullanıcının ne sorduğunu doğru anlamaya çalış. Soru eksik veya belirsizse tahmin yürütmek yerine kısaca açıklama iste.
9. Teknik sorularda gerektiğinde kısa ve çalışan bir örnek ver ama konudan uzaklaşma.
10. Sohbetlerde doğal, samimi ve saygılı bir dil kullan.

Örnek Doğru Üslup Kalıpları:
- Belirsizlik ilkesi sorulduğunda: "Emin olmadığım konularda kesin konuşmam. Bilgimden emin değilsem bunu açıkça söylerim ve tahminlerimi gerçek bilgi gibi sunmam."
- Bilinemeyecek bir detay sorulduğunda: "Bu konuda kesin bir bilgim yok; yanlış yönlendirmemek için tahmin yürütmek istemem."
- Eksik/belirsiz soruda: "Tam olarak neyi kastettiğinizi biraz açabilir misiniz? Hangi konu veya araç için çözüm aradığınızı belirtirseniz hemen yardımcı olabilirim."
- Günlük tavsiye sorulduğunda: "Yemek sonrası rehaveti dağıtmak için bir bardak su içip 5 dakika temiz hava alabilir, ardından telefonunu sessize alıp 20 dakikalık tek bir odaklanma turuyla işini hızlıca bitirebilirsin."
- Basit bilgi sorusunda: Doğrudan tek cümlelik doğru bilgi (gereksiz ek paragraf olmadan)."""

# Yapılandırılmış yaşam döngüsü günlüğü
logger = logging.getLogger("OfflineAIManager")
logger.setLevel(logging.INFO)
if not logger.handlers:
    fh = logging.FileHandler(LIFECYCLE_LOG_PATH, encoding="utf-8")
    fh.setFormatter(logging.Formatter("%(asctime)s [%(levelname)s] %(message)s"))
    logger.addHandler(fh)


def log_shutdown_error(message: str, exc: Exception = None):
    """Kapatma sırasında bir hata oluşursa ayrıntılı hata kaydı oluşturur."""
    timestamp = datetime.datetime.now().isoformat(timespec="seconds")
    detail = f"{timestamp} [SHUTDOWN_ERROR] {message}"
    if exc:
        detail += f" | Exception: {repr(exc)}"
    logger.error(detail)
    with open(SHUTDOWN_ERROR_LOG_PATH, "a", encoding="utf-8") as f:
        f.write(detail + "\n")


class ChatDatabase:
    """Tüm sohbet geçmişini yerel SQLite veritabanında (data/chats.db) saklar."""

    def __init__(self, db_path: Path = DB_PATH):
        self.db_path = db_path
        self._lock = threading.Lock()
        self._init_db()

    def _connect(self):
        conn = sqlite3.connect(str(self.db_path), timeout=15.0, check_same_thread=False)
        conn.row_factory = sqlite3.Row
        conn.execute("PRAGMA journal_mode=WAL;")
        conn.execute("PRAGMA synchronous=NORMAL;")
        conn.execute("PRAGMA foreign_keys=ON;")
        return conn

    def _init_db(self):
        with self._lock:
            with self._connect() as conn:
                conn.execute(
                    """
                    CREATE TABLE IF NOT EXISTS conversations (
                        id TEXT PRIMARY KEY,
                        title TEXT NOT NULL,
                        model TEXT NOT NULL,
                        system_prompt TEXT NOT NULL,
                        created_at TEXT NOT NULL,
                        updated_at TEXT NOT NULL
                    )
                    """
                )
                conn.execute(
                    """
                    CREATE TABLE IF NOT EXISTS messages (
                        id INTEGER PRIMARY KEY AUTOINCREMENT,
                        conversation_id TEXT NOT NULL,
                        role TEXT NOT NULL,
                        content TEXT NOT NULL,
                        created_at TEXT NOT NULL,
                        metrics_json TEXT DEFAULT '{}',
                        FOREIGN KEY (conversation_id) REFERENCES conversations(id) ON DELETE CASCADE
                    )
                    """
                )
                conn.execute(
                    """
                    CREATE TABLE IF NOT EXISTS app_settings (
                        key TEXT PRIMARY KEY,
                        value TEXT NOT NULL
                    )
                    """
                )
                # Mevcut konuşmaların sistem talimatlarını güncel Türkçe kalite kurallarıyla senkronize et
                conn.execute(
                    "UPDATE conversations SET system_prompt = ?",
                    (DEFAULT_SYSTEM_PROMPT,),
                )
                conn.commit()

    def create_conversation(self, title: str = "Yeni Sohbet", model: str = DEFAULT_MODEL, system_prompt: str = DEFAULT_SYSTEM_PROMPT) -> dict:
        now = datetime.datetime.now().isoformat(timespec="seconds")
        conv_id = str(uuid.uuid4())
        with self._lock:
            with self._connect() as conn:
                conn.execute(
                    "INSERT INTO conversations (id, title, model, system_prompt, created_at, updated_at) VALUES (?, ?, ?, ?, ?, ?)",
                    (conv_id, title, model, system_prompt, now, now),
                )
                conn.commit()
        return {
            "id": conv_id,
            "title": title,
            "model": model,
            "system_prompt": system_prompt,
            "created_at": now,
            "updated_at": now,
        }

    def list_conversations(self) -> list:
        with self._lock:
            with self._connect() as conn:
                rows = conn.execute(
                    """
                    SELECT c.*, COUNT(m.id) AS message_count
                    FROM conversations c
                    LEFT JOIN messages m ON m.conversation_id = c.id
                    GROUP BY c.id
                    ORDER BY c.updated_at DESC
                    """
                ).fetchall()
                return [dict(r) for r in rows]

    def get_conversation(self, conv_id: str) -> dict:
        with self._lock:
            with self._connect() as conn:
                conv = conn.execute("SELECT * FROM conversations WHERE id = ?", (conv_id,)).fetchone()
                if not conv:
                    return None
                msgs = conn.execute(
                    "SELECT * FROM messages WHERE conversation_id = ? ORDER BY id ASC", (conv_id,)
                ).fetchall()
                res = dict(conv)
                res["messages"] = [dict(m) for m in msgs]
                return res

    def add_message(self, conv_id: str, role: str, content: str, metrics: dict = None) -> dict:
        now = datetime.datetime.now().isoformat(timespec="seconds")
        metrics_str = json.dumps(metrics or {}, ensure_ascii=False)
        with self._lock:
            with self._connect() as conn:
                cur = conn.execute(
                    "INSERT INTO messages (conversation_id, role, content, created_at, metrics_json) VALUES (?, ?, ?, ?, ?)",
                    (conv_id, role, content, now, metrics_str),
                )
                msg_id = cur.lastrowid
                # Başlık hala "Yeni Sohbet" ise ilk kullanıcı mesajından otomatik başlık üret
                if role == "user":
                    conv = conn.execute("SELECT title FROM conversations WHERE id = ?", (conv_id,)).fetchone()
                    if conv and conv["title"] == "Yeni Sohbet":
                        short_title = content.strip().replace("\n", " ")[:48]
                        if len(content.strip()) > 48:
                            short_title += "..."
                        conn.execute(
                            "UPDATE conversations SET title = ?, updated_at = ? WHERE id = ?",
                            (short_title or "Sohbet", now, conv_id),
                        )
                    else:
                        conn.execute("UPDATE conversations SET updated_at = ? WHERE id = ?", (now, conv_id))
                else:
                    conn.execute("UPDATE conversations SET updated_at = ? WHERE id = ?", (now, conv_id))
                conn.commit()
        return {
            "id": msg_id,
            "conversation_id": conv_id,
            "role": role,
            "content": content,
            "created_at": now,
            "metrics_json": metrics_str,
        }

    def rename_conversation(self, conv_id: str, new_title: str) -> bool:
        now = datetime.datetime.now().isoformat(timespec="seconds")
        with self._lock:
            with self._connect() as conn:
                cur = conn.execute(
                    "UPDATE conversations SET title = ?, updated_at = ? WHERE id = ?",
                    (new_title.strip() or "Sohbet", now, conv_id),
                )
                conn.commit()
                return cur.rowcount > 0

    def delete_conversation(self, conv_id: str) -> bool:
        with self._lock:
            with self._connect() as conn:
                cur = conn.execute("DELETE FROM conversations WHERE id = ?", (conv_id,))
                conn.commit()
                return cur.rowcount > 0

    def get_stats(self) -> dict:
        with self._lock:
            with self._connect() as conn:
                c_count = conn.execute("SELECT COUNT(*) FROM conversations").fetchone()[0]
                m_count = conn.execute("SELECT COUNT(*) FROM messages").fetchone()[0]
        size_bytes = self.db_path.stat().st_size if self.db_path.exists() else 0
        return {
            "db_path": str(self.db_path),
            "conversations_count": c_count,
            "messages_count": m_count,
            "db_size_bytes": size_bytes,
            "db_size_kb": round(size_bytes / 1024.0, 2),
        }

    def create_backup(self, tag: str = "manual") -> dict:
        """Veritabanını hem güvenli SQLite kopyası hem de JSON ve Markdown olarak yedekler."""
        ts = datetime.datetime.now().strftime("%Y%m%d_%H%M%S")
        zip_path = BACKUP_DIR / f"chat_backup_{ts}_{tag}.zip"
        tmp_db = BACKUP_DIR / f"chats_{ts}.db"

        with self._lock:
            with self._connect() as src_conn:
                dst_conn = sqlite3.connect(str(tmp_db))
                src_conn.backup(dst_conn)
                dst_conn.close()

        convs = self.list_conversations()
        full_export = []
        for c in convs:
            full_export.append(self.get_conversation(c["id"]))

        with zipfile.ZipFile(zip_path, "w", compression=zipfile.ZIP_DEFLATED) as zf:
            zf.write(tmp_db, arcname="chats.db")
            zf.writestr(
                "chats_export.json",
                json.dumps(
                    {
                        "exported_at": datetime.datetime.now().isoformat(timespec="seconds"),
                        "total_conversations": len(full_export),
                        "conversations": full_export,
                    },
                    ensure_ascii=False,
                    indent=2,
                ),
            )
            for conv in full_export:
                if not conv:
                    continue
                md_lines = [
                    f"# {conv['title']}",
                    f"- **ID:** `{conv['id']}`",
                    f"- **Model:** `{conv['model']}`",
                    f"- **Oluşturulma:** {conv['created_at']}",
                    "",
                    "---",
                    "",
                ]
                for m in conv.get("messages", []):
                    role_label = "Kullanıcı" if m["role"] == "user" else "AI Asistan"
                    md_lines.append(f"### {role_label} ({m['created_at']})\n\n{m['content']}\n")
                safe_id = conv["id"][:8]
                zf.writestr(f"markdown/sohbet_{safe_id}.md", "\n".join(md_lines))

        if tmp_db.exists():
            tmp_db.unlink()

        logger.info(f"Sohbet yedeği oluşturuldu: {zip_path} ({len(full_export)} konuşma)")
        return {
            "backup_path": str(zip_path),
            "conversations_backed_up": len(full_export),
            "size_kb": round(zip_path.stat().st_size / 1024.0, 2),
            "timestamp": ts,
        }


class MEMORYSTATUSEX(ctypes.Structure):
    _fields_ = [
        ("dwLength", ctypes.c_ulong),
        ("dwMemoryLoad", ctypes.c_ulong),
        ("ullTotalPhys", ctypes.c_ulonglong),
        ("ullAvailPhys", ctypes.c_ulonglong),
        ("ullTotalPageFile", ctypes.c_ulonglong),
        ("ullAvailPageFile", ctypes.c_ulonglong),
        ("ullTotalVirtual", ctypes.c_ulonglong),
        ("ullAvailVirtual", ctypes.c_ulonglong),
        ("sullAvailExtendedVirtual", ctypes.c_ulonglong),
    ]


def get_system_ram_info() -> dict:
    stat = MEMORYSTATUSEX()
    stat.dwLength = ctypes.sizeof(MEMORYSTATUSEX)
    ctypes.windll.kernel32.GlobalMemoryStatusEx(ctypes.byref(stat))
    total_mb = stat.ullTotalPhys / (1024 * 1024)
    avail_mb = stat.ullAvailPhys / (1024 * 1024)
    used_mb = total_mb - avail_mb
    return {
        "total_mb": round(total_mb, 1),
        "used_mb": round(used_mb, 1),
        "avail_mb": round(avail_mb, 1),
        "percent": stat.dwMemoryLoad,
    }


def get_ollama_processes_memory_mb() -> dict:
    """Çalışan ollama ve llama-server (model runner) süreçlerinin PID listesini ve toplam RAM kullanımını döndürür."""
    try:
        cmd = [
            "powershell",
            "-NoProfile",
            "-Command",
            "Get-Process *ollama*, *llama-server* -ErrorAction SilentlyContinue | Select-Object Id, ProcessName, WorkingSet64 | ConvertTo-Json -Compress",
        ]
        res = subprocess.run(cmd, capture_output=True, text=True, timeout=4, creationflags=subprocess.CREATE_NO_WINDOW)
        out = res.stdout.strip()
        if not out:
            return {"count": 0, "total_ram_mb": 0.0, "processes": []}
        data = json.loads(out)
        if isinstance(data, dict):
            data = [data]
        total_ws = sum(int(p.get("WorkingSet64", 0)) for p in data)
        return {
            "count": len(data),
            "total_ram_mb": round(total_ws / (1024 * 1024), 1),
            "processes": [
                {
                    "pid": p.get("Id"),
                    "name": p.get("ProcessName"),
                    "ram_mb": round(int(p.get("WorkingSet64", 0)) / (1024 * 1024), 1),
                }
                for p in data
            ],
        }
    except Exception:
        return {"count": 0, "total_ram_mb": 0.0, "processes": []}


class OllamaLifecycleManager:
    """
    Ollama servisini, modeli, aktif üretimi ve 5 aşamalı güvenli kapatma sürecini yönetir.
    """

    def __init__(self, db: ChatDatabase):
        self.db = db
        self.model_name = DEFAULT_MODEL
        self.ollama_proc = None
        self._stream_lock = threading.Lock()
        self._cancel_event = threading.Event()
        self._active_response = None
        self._is_generating = False
        self._shutdown_lock = threading.Lock()
        self._shutdown_completed = False

    def _privacy_env(self) -> dict:
        env = os.environ.copy()
        env["OLLAMA_HOST"] = OLLAMA_HOST
        env["OLLAMA_ORIGINS"] = "http://127.0.0.1:*,http://localhost:*"
        env["OLLAMA_NO_CLOUD"] = "1"
        env["DO_NOT_TRACK"] = "1"
        env["SCARF_NO_ANALYTICS"] = "true"
        env["ANONYMIZED_TELEMETRY"] = "false"
        env["HF_HUB_OFFLINE"] = "1"
        env["TRANSFORMERS_OFFLINE"] = "1"
        return env

    def is_server_online(self) -> bool:
        try:
            req = urllib.request.Request(f"{OLLAMA_BASE_URL}/api/version", method="GET")
            with urllib.request.urlopen(req, timeout=1.5) as resp:
                return resp.status == 200
        except Exception:
            return False

    def get_loaded_models(self) -> list:
        """Ollama /api/ps üzerinden bellekte (VRAM/RAM) yüklü modelleri sorgular."""
        if not self.is_server_online():
            return []
        try:
            req = urllib.request.Request(f"{OLLAMA_BASE_URL}/api/ps", method="GET")
            with urllib.request.urlopen(req, timeout=2.0) as resp:
                data = json.loads(resp.read().decode("utf-8"))
                models = data.get("models", [])
                result = []
                for m in models:
                    size_total = int(m.get("size", 0))
                    size_vram = int(m.get("size_vram", 0))
                    gpu_pct = round((size_vram / size_total) * 100, 1) if size_total > 0 else 0.0
                    result.append(
                        {
                            "name": m.get("name"),
                            "size_mb": round(size_total / (1024 * 1024), 1),
                            "vram_mb": round(size_vram / (1024 * 1024), 1),
                            "ram_offload_mb": round(max(0, size_total - size_vram) / (1024 * 1024), 1),
                            "gpu_percent": gpu_pct,
                            "processor": f"{gpu_pct}% GPU (ROCm RX 7600)" if gpu_pct > 0 else "CPU",
                            "expires_at": m.get("expires_at", ""),
                        }
                    )
                return result
        except Exception:
            return []

    def set_active_model(self, model_name: str) -> dict:
        if model_name and model_name != self.model_name:
            old = self.model_name
            self.model_name = model_name
            logger.info(f"Varsayılan model değiştirildi: {old} -> {model_name}")
        return self.get_status()

    def get_status(self) -> dict:
        online = self.is_server_online()
        loaded = self.get_loaded_models() if online else []
        proc_mem = get_ollama_processes_memory_mb()
        sys_ram = get_system_ram_info()
        vram_used_mb = sum(m["vram_mb"] for m in loaded)
        return {
            "ollama_online": online,
            "ollama_host": OLLAMA_HOST,
            "default_model": self.model_name,
            "model_loaded": len(loaded) > 0,
            "loaded_models": loaded,
            "vram_used_mb": round(vram_used_mb, 1),
            "ollama_ram_mb": proc_mem["total_ram_mb"],
            "ollama_process_count": proc_mem["count"],
            "system_ram": sys_ram,
            "is_generating": self._is_generating,
            "db_stats": self.db.get_stats(),
        }

    def start_ollama(self, preload_model: bool = False) -> dict:
        """Ollama arka plan servisini yalnızca localhost (127.0.0.1:11434) üzerinde başlatır."""
        self._shutdown_completed = False
        if not self.is_server_online():
            logger.info("Ollama servisi başlatılıyor (127.0.0.1:11434, OLLAMA_NO_CLOUD=1)...")
            stdout_log = open(LOG_DIR / "ollama_stdout.log", "a", encoding="utf-8")
            stderr_log = open(LOG_DIR / "ollama_stderr.log", "a", encoding="utf-8")
            self.ollama_proc = subprocess.Popen(
                [str(OLLAMA_EXE), "serve"],
                env=self._privacy_env(),
                stdout=stdout_log,
                stderr=stderr_log,
                creationflags=subprocess.CREATE_NO_WINDOW | subprocess.CREATE_NEW_PROCESS_GROUP,
            )
            for _ in range(30):
                if self.is_server_online():
                    break
                time.sleep(0.3)
            logger.info(f"Ollama servisi durumu: online={self.is_server_online()}")

        if preload_model and self.is_server_online():
            self.preload_model()

        return self.get_status()

    def preload_model(self) -> bool:
        """Modeli boş bir istekle GPU VRAM'e önceden yükler."""
        if not self.is_server_online():
            self.start_ollama(preload_model=False)
        try:
            logger.info(f"Model belleğe yükleniyor: {self.model_name}")
            payload = json.dumps({"model": self.model_name, "keep_alive": "10m"}).encode("utf-8")
            req = urllib.request.Request(
                f"{OLLAMA_BASE_URL}/api/generate",
                data=payload,
                headers={"Content-Type": "application/json"},
                method="POST",
            )
            with urllib.request.urlopen(req, timeout=60) as resp:
                resp.read()
            logger.info(f"Model belleğe yüklendi: {self.get_loaded_models()}")
            return True
        except Exception as exc:
            logger.error(f"Model yükleme hatası: {exc}")
            return False

    def cancel_active_generation(self) -> bool:
        """1. Adım: Devam eden AI üretimini güvenli şekilde durdurur."""
        self._cancel_event.set()
        was_generating = self._is_generating
        if was_generating:
            logger.info("[ADIM 1] Devam eden AI üretimi durdurma sinyali gönderildi.")
        with self._stream_lock:
            if self._active_response is not None:
                try:
                    self._active_response.close()
                except Exception:
                    pass
                self._active_response = None
        # Üretim iş parçacığının kapanmasını bekle
        for _ in range(25):
            if not self._is_generating:
                break
            time.sleep(0.1)
        logger.info(f"[ADIM 1] Aktif üretim güvenli şekilde durduruldu (önceden aktif miydi: {was_generating}).")
        return True

    def unload_model(self) -> dict:
        """
        2. ve 3. Adım: Ollama'ya çalışan modeli durdurma komutu gönderir (`ollama stop MODEL_ADI`)
        ve VRAM/RAM kullanımının serbest bırakıldığını doğrular.
        """
        self.cancel_active_generation()
        before_loaded = self.get_loaded_models()
        before_vram_mb = sum(m["vram_mb"] for m in before_loaded)
        before_ram = get_ollama_processes_memory_mb()["total_ram_mb"]

        models_to_stop = [m["name"] for m in before_loaded]
        if self.model_name not in models_to_stop:
            models_to_stop.append(self.model_name)

        if self.is_server_online():
            for m_name in models_to_stop:
                try:
                    logger.info(f"[ADIM 2] 'ollama stop {m_name}' komutu çalıştırılıyor...")
                    proc = subprocess.run(
                        [str(OLLAMA_EXE), "stop", m_name],
                        env=self._privacy_env(),
                        capture_output=True,
                        text=True,
                        timeout=15,
                        creationflags=subprocess.CREATE_NO_WINDOW,
                    )
                    logger.info(
                        f"[ADIM 2] 'ollama stop {m_name}' tamamlandı (kod={proc.returncode})."
                    )
                except Exception as exc:
                    log_shutdown_error(f"'ollama stop {m_name}' çalıştırılırken hata oluştu", exc)

            # Doğrulama: /api/ps boşalana kadar bekle
            for _ in range(25):
                if len(self.get_loaded_models()) == 0:
                    break
                time.sleep(0.2)

        after_loaded = self.get_loaded_models()
        after_vram_mb = sum(m["vram_mb"] for m in after_loaded)
        after_ram = get_ollama_processes_memory_mb()["total_ram_mb"]
        vram_freed = round(max(0.0, before_vram_mb - after_vram_mb), 1)
        ram_freed = round(max(0.0, before_ram - after_ram), 1)

        verified = len(after_loaded) == 0
        logger.info(
            f"[ADIM 3] Bellek doğrulaması: Yüklü model sayısı={len(after_loaded)}, "
            f"Önceki VRAM={before_vram_mb} MB -> Sonraki VRAM={after_vram_mb} MB (Serbest kalan VRAM={vram_freed} MB), "
            f"Önceki Ollama RAM={before_ram} MB -> Sonraki Ollama RAM={after_ram} MB. Doğrulandı={verified}"
        )
        if not verified:
            log_shutdown_error(f"Model bellekten tamamen kaldırılamadı! Kalan modeller: {after_loaded}")

        return {
            "verified_unloaded": verified,
            "before_vram_mb": before_vram_mb,
            "after_vram_mb": after_vram_mb,
            "vram_freed_mb": vram_freed,
            "before_ram_mb": before_ram,
            "after_ram_mb": after_ram,
            "ram_freed_mb": ram_freed,
        }

    def stop_ollama_service_gracefully(self) -> bool:
        """
        4. Adım: Ollama arka plan servisini zorla sonlandırmayı (/F) İLK SEÇENEK OLARAK KULLANMADAN
        güvenli şekilde kapatır.
        """
        logger.info("[ADIM 4] Ollama arka plan servisi güvenli şekilde kapatılıyor (zorla kapatma olmadan)...")
        try:
            # 4a: Bizim başlattığımız alt süreç varsa önce CTRL_BREAK_EVENT / terminate gönder
            if self.ollama_proc and self.ollama_proc.poll() is None:
                try:
                    self.ollama_proc.send_signal(signal.CTRL_BREAK_EVENT)
                    self.ollama_proc.wait(timeout=4)
                    logger.info("[ADIM 4] Ollama alt süreci CTRL_BREAK_EVENT ile güvenli şekilde kapandı.")
                except Exception:
                    try:
                        self.ollama_proc.terminate()
                        self.ollama_proc.wait(timeout=3)
                    except Exception:
                        pass

            # 4b: Diğer ollama süreçleri varsa önce /F OLMADAN nazik taskkill veya CloseMainWindow dene
            proc_info = get_ollama_processes_memory_mb()
            if proc_info["count"] > 0:
                subprocess.run(
                    ["taskkill", "/IM", "ollama app.exe"],
                    capture_output=True,
                    text=True,
                    timeout=5,
                    creationflags=subprocess.CREATE_NO_WINDOW,
                )
                subprocess.run(
                    ["taskkill", "/IM", "ollama.exe"],
                    capture_output=True,
                    text=True,
                    timeout=5,
                    creationflags=subprocess.CREATE_NO_WINDOW,
                )
                for _ in range(15):
                    if get_ollama_processes_memory_mb()["count"] == 0:
                        break
                    time.sleep(0.2)

            # 4c: Nazik kapatma sinyaline rağmen hala konsol arka plan süreci kaldıysa son çare olarak temizle
            remaining = get_ollama_processes_memory_mb()
            if remaining["count"] > 0:
                logger.info(
                    f"[ADIM 4] Nazik sinyal sonrası {remaining['count']} konsol süreci hala açık, sonlandırma tamamlanıyor..."
                )
                subprocess.run(
                    [
                        "powershell",
                        "-NoProfile",
                        "-Command",
                        "Get-Process *ollama*, *llama-server* -ErrorAction SilentlyContinue | Stop-Process -ErrorAction SilentlyContinue",
                    ],
                    capture_output=True,
                    text=True,
                    timeout=5,
                    creationflags=subprocess.CREATE_NO_WINDOW,
                )
                for _ in range(10):
                    if get_ollama_processes_memory_mb()["count"] == 0:
                        break
                    time.sleep(0.2)

            final_check = get_ollama_processes_memory_mb()
            stopped_ok = (final_check["count"] == 0) and (not self.is_server_online())
            logger.info(
                f"[ADIM 4] Ollama arka plan servisi kapatma sonucu: başarılı={stopped_ok}, kalan süreç={final_check['count']}"
            )
            if not stopped_ok:
                log_shutdown_error(f"Ollama servisi tamamen kapatılamadı. Kalan süreçler: {final_check}")
            return stopped_ok
        except Exception as exc:
            log_shutdown_error("Ollama servisi kapatılırken istisna oluştu", exc)
            return False

    def execute_ordered_shutdown(self, trigger_source: str = "NORMAL_EXIT") -> dict:
        """
        Kullanıcının istediği tam sıralı kapatma prosedürü:
        1. Devam eden AI üretimini güvenli şekilde durdur.
        2. Ollama'ya çalışan modeli durdurma komutu gönder (`ollama stop MODEL_ADI`).
        3. Modelin VRAM ve RAM kullanımının serbest bırakıldığını doğrula.
        4. Ardından Ollama arka plan servisini güvenli şekilde kapat.
        5. Sohbet geçmişini ve veritabanını kesinlikle silme (korunduğunu doğrula).
        """
        with self._shutdown_lock:
            if self._shutdown_completed and trigger_source != "STOP_AI_BUTTON":
                logger.info(f"Kapatma prosedürü zaten tamamlandı (tetikleyici: {trigger_source}).")
                return {"already_shut_down": True}

            logger.info("=" * 72)
            logger.info(f"OTOMATİK KAPATMA BAŞLATILDI | Tetikleyici: {trigger_source}")
            try:
                # 1. Üretimi durdur
                self.cancel_active_generation()

                # 2. ve 3. Modeli durdur ve VRAM/RAM boşaldığını doğrula
                unload_res = self.unload_model()

                # 4. Ollama arka plan servisini güvenli kapat
                service_stopped = self.stop_ollama_service_gracefully()

                # 5. Veritabanının ve sohbet geçmişinin korunduğunu doğrula
                db_stats = self.db.get_stats()
                db_preserved = DB_PATH.exists()
                logger.info(
                    f"[ADIM 5] Veritabanı koruma doğrulaması: {DB_PATH} mevcut={db_preserved}, "
                    f"Konuşma sayısı={db_stats['conversations_count']}, Mesaj sayısı={db_stats['messages_count']}"
                )
                logger.info(f"OTOMATİK KAPATMA TAMAMLANDI | Tetikleyici: {trigger_source}")
                logger.info("=" * 72)

                if trigger_source != "STOP_AI_BUTTON":
                    self._shutdown_completed = True

                return {
                    "trigger": trigger_source,
                    "step1_generation_stopped": True,
                    "step2_and_3_unload": unload_res,
                    "step4_service_stopped": service_stopped,
                    "step5_db_preserved": db_preserved,
                    "db_stats": db_stats,
                }
            except Exception as exc:
                log_shutdown_error(f"Sıralı kapatma hatası (Tetikleyici: {trigger_source})", exc)
                return {"error": str(exc)}

    def stream_chat(self, conv_id: str, user_message: str, think: bool = False):
        """
        Kullanıcı mesajını kaydeder, gerekirse Ollama'yı otomatik başlatır,
        yanıtı akış (streaming) olarak üretir ve veritabanına kaydeder.
        think=False -> Hızlı Mod (Varsayılan)
        think=True  -> Derin Düşünme Modu (Qwen3 resmi reasoning modu)
        """
        self._cancel_event.clear()
        self._is_generating = True
        use_think = bool(think)

        # Uygulama veya servis kapalıysa otomatik başlat ("Uygulama yeniden açıldığında Ollama servisini ve modeli gerektiğinde otomatik başlat")
        if not self.is_server_online():
            self.start_ollama(preload_model=False)

        conv = self.db.get_conversation(conv_id)
        if not conv:
            conv = self.db.create_conversation()
            conv_id = conv["id"]
            conv = self.db.get_conversation(conv_id)

        self.db.add_message(conv_id, "user", user_message)
        conv = self.db.get_conversation(conv_id)

        messages_payload = [{"role": "system", "content": DEFAULT_SYSTEM_PROMPT}]
        for m in conv.get("messages", []):
            messages_payload.append({"role": m["role"], "content": m["content"]})

        payload = json.dumps(
            {
                "model": conv.get("model") or self.model_name,
                "messages": messages_payload,
                "stream": True,
                "think": use_think,
                "keep_alive": "10m",
                "options": {
                    "temperature": 0.2,
                    "top_p": 0.85,
                    "repeat_penalty": 1.12,
                    "num_ctx": 4096,
                },
            }
        ).encode("utf-8")

        full_reply = []
        full_thinking = []
        metrics = {}
        start_time = time.time()

        try:
            req = urllib.request.Request(
                f"{OLLAMA_BASE_URL}/api/chat",
                data=payload,
                headers={"Content-Type": "application/json"},
                method="POST",
            )
            resp = urllib.request.urlopen(req, timeout=240)
            with self._stream_lock:
                self._active_response = resp

            for raw_line in resp:
                if self._cancel_event.is_set():
                    full_reply.append("\n\n*[Üretim kullanıcı tarafından durduruldu]*")
                    yield {"type": "chunk", "content": "\n\n*[Üretim kullanıcı tarafından durduruldu]*"}
                    break
                line = raw_line.decode("utf-8").strip()
                if not line:
                    continue
                chunk_obj = json.loads(line)
                msg_obj = chunk_obj.get("message", {})
                thinking_token = msg_obj.get("thinking", "")
                if thinking_token:
                    full_thinking.append(thinking_token)
                    yield {"type": "thinking", "content": thinking_token, "thinking_chars": sum(len(x) for x in full_thinking)}
                token = msg_obj.get("content", "")
                if token:
                    full_reply.append(token)
                    yield {"type": "chunk", "content": token}
                if chunk_obj.get("done"):
                    eval_count = chunk_obj.get("eval_count", 0)
                    eval_duration_ns = chunk_obj.get("eval_duration", 1)
                    tok_per_sec = round(eval_count / (eval_duration_ns / 1e9), 2) if eval_duration_ns > 0 else 0.0
                    thinking_text = "".join(full_thinking).strip()
                    metrics = {
                        "eval_count": eval_count,
                        "tokens_per_sec": tok_per_sec,
                        "total_duration_s": round(time.time() - start_time, 2),
                        "think_mode": use_think,
                        "mode_label": "Derin Düşünme" if use_think else "Hızlı Mod",
                        "thinking_active": len(thinking_text) > 0,
                        "thinking_chars": len(thinking_text),
                    }
                    logger.info(
                        f"Sohbet yanıtı tamamlandı | think={use_think} ({metrics['mode_label']}) | "
                        f"thinking_chars={metrics['thinking_chars']} | eval_count={eval_count} | {tok_per_sec} tok/sn"
                    )
                    break
        except Exception as exc:
            if self._cancel_event.is_set():
                full_reply.append("\n\n*[Üretim güvenli şekilde durduruldu]*")
            else:
                err_txt = f"\n\n*[Yerel model bağlantı hatası: {exc}]*"
                full_reply.append(err_txt)
                yield {"type": "error", "content": err_txt}
        finally:
            with self._stream_lock:
                if self._active_response is not None:
                    try:
                        self._active_response.close()
                    except Exception:
                        pass
                    self._active_response = None
            self._is_generating = False

        assistant_text = "".join(full_reply).strip()
        if assistant_text:
            saved_msg = self.db.add_message(conv_id, "assistant", assistant_text, metrics=metrics)
            yield {
                "type": "done",
                "message": saved_msg,
                "metrics": metrics,
                "conversation": self.db.get_conversation(conv_id),
            }
        else:
            yield {"type": "done", "message": None, "metrics": metrics}
