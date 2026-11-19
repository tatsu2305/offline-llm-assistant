# Personal Offline AI Assistant — Local LLM Desktop Runtime

**Language:** Python, PowerShell · **Core Stack:** Ollama (`Qwen3 8B` / `Qwen2.5 7B` 4-Bit GGUF), PyWebView, PyStray, SQLite (WAL), Windows Firewall Automation

A privacy-first, 100% localhost (`127.0.0.1`) desktop application and lifecycle manager for running quantized local Large Language Models on consumer hardware (8 GB VRAM GPU / 16 GB RAM) with zero cloud API dependencies and deterministic VRAM/RAM cleanup.

---

## Overview & Motivation

Running local LLMs via background services often leaves heavy model weights resident in GPU VRAM and system RAM after the user finishes chatting—impacting gaming, CAD, or development workloads on mid-range hardware (e.g., Intel i3-13100F, AMD Radeon RX 7600 8 GB VRAM, 16 GB RAM).

This project wraps local Ollama inference in a self-contained desktop UI (`PyWebView` + system tray control) paired with an automated lifecycle controller (`OllamaLifecycleManager`) that guarantees clean resource release upon exit.

---

## Key Features

- **100% Offline & Localhost-Only (`127.0.0.1`):**
  - Strictly binds the internal HTTP server (`127.0.0.1:18450`) and Ollama bridge (`127.0.0.1:11434`) to loopback with a restrictive Content-Security-Policy (`connect-src 'self'`).
  - Includes a PowerShell firewall hardening script (`firewall_offline_lock.ps1`) to block outbound external traffic for offline isolation.
- **Deterministic VRAM & Service Teardown (`OllamaLifecycleManager`):**
  - When closed via the window `X` button, System Tray `Quit / Exit`, or process signal:
    1. Cancels any active token generation stream safely.
    2. Issues `ollama stop` to unload quantized model weights from GPU VRAM / system RAM.
    3. Verifies memory release and terminates the background Ollama server process.
    4. Flushes and closes the local SQLite database cleanly.
- **Thread-Safe SQLite Conversation Storage (`ChatDatabase`):**
  - Stores multi-session conversation history locally in `data/chats.db` using SQLite Write-Ahead Logging (`PRAGMA journal_mode=WAL`).
  - Includes an automated ZIP backup utility (`backup_chats.py` / `Sohbet_Yedekle.bat`).
- **Turkish Language Quality & Verification Suite:**
  - Configured with a strict 10-rule Turkish system prompt preventing hallucination and enforcing concise, natural responses.
  - Includes automated verification scripts (`verify_all.py`, `test_turkish_quality.py`) to test model response quality and lifecycle behavior.

---

## Project Structure

```text
├── app.py                        # Desktop UI (PyWebView), local HTTP API & System Tray (PyStray)
├── ai_manager.py                 # OllamaLifecycleManager, SQLite WAL ChatDatabase & shutdown hooks
├── backup_chats.py               # Conversation database backup utility (ZIP archive export)
├── firewall_offline_lock.ps1     # Windows Firewall script enforcing offline localhost-only execution
├── test_turkish_quality.py       # Automated prompt & Turkish response quality evaluation
├── verify_all.py                 # End-to-end system & lifecycle verification script
├── requirements.txt              # Python package dependencies (pywebview, pystray, Pillow)
├── AI_Baslat.bat                 # One-click desktop launcher
├── AI_Tamamen_Durdur.bat         # Emergency full process & service stop script
├── Modeli_Bellekten_Kaldir.bat   # Quick VRAM/RAM model unload shortcut
└── Sohbet_Yedekle.bat            # One-click chat history backup shortcut
```

---

## Requirements & Hardware Target

- **OS:** Windows 10 / 11 (x64)
- **Reference Hardware:** Intel Core i3-13100F · AMD Radeon RX 7600 (8 GB VRAM) · 16 GB DDR4 RAM
- **Runtime:** Python 3.10+, [Ollama](https://ollama.com/) installed locally with `qwen3:8b` or `qwen2.5:7b-instruct-q4_K_M`
- **Python Packages:** `pywebview`, `pystray`, `Pillow`

---

## Usage

```powershell
# Install Python dependencies
pip install -r requirements.txt

# Launch the desktop application
python app.py

# Run system & lifecycle verification
python verify_all.py

# Backup local SQLite conversation database
python backup_chats.py
```
