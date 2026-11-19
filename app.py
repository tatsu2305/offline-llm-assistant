# -*- coding: utf-8 -*-
"""
Kişisel Offline AI Masaüstü Uygulaması (ChatGPT Benzeri Yerel Arayüz + Sistem Tepsisi + Otomatik Kapatma)
- Yalnızca 127.0.0.1 (localhost) üzerinde çalışır.
- Pencerenin sağ üstündeki X butonuna basıldığında, Sistem Tepsisinden Quit / Exit seçildiğinde
  veya uygulama normal şekilde kapatıldığında:
    1) Devam eden AI üretimini güvenli şekilde durdurur.
    2) `ollama stop qwen2.5:7b-instruct-q4_K_M` komutunu gönderir.
    3) VRAM ve RAM'in serbest bırakıldığını doğrular.
    4) Ollama arka plan servisini güvenli şekilde kapatır.
    5) Sohbet geçmişini (data/chats.db) korur.
"""

import argparse
import http.server
import json
import os
import socketserver
import sys
import threading
import time
import urllib.parse
from pathlib import Path
from PIL import Image, ImageDraw
import pystray
import webview

from ai_manager import (
    ChatDatabase,
    OllamaLifecycleManager,
    DEFAULT_MODEL,
    LIFECYCLE_LOG_PATH,
    logger,
)

APP_HOST = "127.0.0.1"
APP_PORT = 18450

db = ChatDatabase()
manager = OllamaLifecycleManager(db)

# Uygulama penceresi ve sistem tepsisi referansları
_webview_window = None
_tray_icon = None
_http_server = None
_app_exiting = threading.Event()


HTML_UI = r"""<!DOCTYPE html>
<html lang="tr">
<head>
<meta charset="UTF-8">
<meta name="viewport" content="width=device-width, initial-scale=1.0">
<meta http-equiv="Content-Security-Policy" content="default-src 'self' 'unsafe-inline' data:; connect-src 'self'; img-src 'self' data:;">
<title>Kişisel Offline AI — Qwen3 8B (4-Bit Q4_K_M | Yerel & Gizli)</title>
<style>
  :root {
    --bg-main: #0f1117;
    --bg-sidebar: #161922;
    --bg-card: #1e2230;
    --bg-input: #232838;
    --bg-user: #2b5278;
    --bg-ai: #1a1e2b;
    --text-primary: #eef1f8;
    --text-secondary: #9aa3b8;
    --accent: #10a37f;
    --accent-hover: #0d8a6a;
    --warn: #f59e0b;
    --danger: #ef4444;
    --border: #2a3042;
  }
  * { box-sizing: border-box; margin: 0; padding: 0; }
  body {
    font-family: "Segoe UI", system-ui, -apple-system, sans-serif;
    background: var(--bg-main);
    color: var(--text-primary);
    height: 100vh;
    display: flex;
    overflow: hidden;
    user-select: text;
  }
  /* SOL KENAR ÇUBUĞU (SIDEBAR) */
  .sidebar {
    width: 290px;
    background: var(--bg-sidebar);
    border-right: 1px solid var(--border);
    display: flex;
    flex-direction: column;
    flex-shrink: 0;
  }
  .sidebar-header {
    padding: 16px;
    border-bottom: 1px solid var(--border);
  }
  .brand {
    display: flex;
    align-items: center;
    gap: 10px;
    font-weight: 700;
    font-size: 15px;
    margin-bottom: 12px;
    color: #fff;
  }
  .brand-dot {
    width: 10px;
    height: 10px;
    border-radius: 50%;
    background: var(--accent);
    box-shadow: 0 0 8px var(--accent);
  }
  .btn-new-chat {
    width: 100%;
    padding: 10px 14px;
    background: var(--accent);
    color: #fff;
    border: none;
    border-radius: 8px;
    font-size: 14px;
    font-weight: 600;
    cursor: pointer;
    display: flex;
    align-items: center;
    justify-content: center;
    gap: 8px;
    transition: background 0.15s;
  }
  .btn-new-chat:hover { background: var(--accent-hover); }
  .search-box {
    padding: 10px 16px;
    border-bottom: 1px solid var(--border);
  }
  .search-box input {
    width: 100%;
    padding: 8px 10px;
    border-radius: 6px;
    border: 1px solid var(--border);
    background: var(--bg-input);
    color: var(--text-primary);
    font-size: 13px;
    outline: none;
  }
  .conv-list {
    flex: 1;
    overflow-y: auto;
    padding: 8px;
  }
  .conv-item {
    padding: 10px 12px;
    border-radius: 8px;
    cursor: pointer;
    display: flex;
    align-items: center;
    justify-content: space-between;
    gap: 8px;
    margin-bottom: 4px;
    transition: background 0.15s;
  }
  .conv-item:hover { background: rgba(255,255,255,0.05); }
  .conv-item.active { background: var(--bg-card); border: 1px solid var(--border); }
  .conv-title {
    font-size: 13.5px;
    white-space: nowrap;
    overflow: hidden;
    text-overflow: ellipsis;
    flex: 1;
  }
  .conv-actions {
    display: flex;
    gap: 4px;
    opacity: 0.65;
  }
  .conv-item:hover .conv-actions { opacity: 1; }
  .icon-btn {
    background: transparent;
    border: none;
    color: var(--text-secondary);
    cursor: pointer;
    font-size: 12px;
    padding: 2px 5px;
    border-radius: 4px;
  }
  .icon-btn:hover { background: rgba(255,255,255,0.1); color: #fff; }
  .sidebar-footer {
    padding: 12px 16px;
    border-top: 1px solid var(--border);
    font-size: 12px;
    color: var(--text-secondary);
    display: flex;
    flex-direction: column;
    gap: 8px;
  }
  .footer-btns {
    display: grid;
    grid-template-columns: 1fr 1fr;
    gap: 6px;
  }
  .btn-small {
    padding: 7px 8px;
    border-radius: 6px;
    border: 1px solid var(--border);
    background: var(--bg-card);
    color: var(--text-primary);
    font-size: 12px;
    cursor: pointer;
    text-align: center;
  }
  .btn-small:hover { background: #2a3044; }
  .btn-small.danger { border-color: rgba(239,68,68,0.4); color: #fca5a5; }
  .btn-small.danger:hover { background: rgba(239,68,68,0.2); }

  /* ANA SOHBET ALANI */
  .main {
    flex: 1;
    display: flex;
    flex-direction: column;
    height: 100vh;
    overflow: hidden;
  }
  .topbar {
    padding: 10px 20px;
    background: var(--bg-sidebar);
    border-bottom: 1px solid var(--border);
    display: flex;
    align-items: center;
    justify-content: space-between;
    flex-wrap: wrap;
    gap: 10px;
  }
  .status-pills {
    display: flex;
    align-items: center;
    gap: 8px;
    flex-wrap: wrap;
  }
  .pill {
    font-size: 12px;
    padding: 4px 10px;
    border-radius: 999px;
    background: var(--bg-card);
    border: 1px solid var(--border);
    display: flex;
    align-items: center;
    gap: 6px;
  }
  .dot { width: 8px; height: 8px; border-radius: 50%; display: inline-block; }
  .dot.on { background: #10b981; box-shadow: 0 0 6px #10b981; }
  .dot.off { background: #ef4444; }
  .dot.idle { background: #f59e0b; }

  .control-bar {
    display: flex;
    align-items: center;
    gap: 6px;
  }
  .ctrl-btn {
    padding: 6px 11px;
    border-radius: 6px;
    border: 1px solid var(--border);
    background: var(--bg-card);
    color: var(--text-primary);
    font-size: 12px;
    font-weight: 500;
    cursor: pointer;
    transition: all 0.15s;
  }
  .ctrl-btn:hover { background: #2c3347; }
  .ctrl-btn.start { border-color: rgba(16,185,129,0.5); color: #6ee7b7; }
  .ctrl-btn.unload { border-color: rgba(245,158,11,0.5); color: #fcd34d; }
  .ctrl-btn.stop { border-color: rgba(239,68,68,0.5); color: #fca5a5; }
  .think-toggle {
    display: inline-flex;
    background: var(--bg-input);
    border: 1px solid var(--border);
    border-radius: 7px;
    padding: 2px;
    gap: 2px;
  }
  .think-opt {
    padding: 5px 10px;
    border-radius: 5px;
    border: none;
    background: transparent;
    color: var(--text-secondary);
    font-size: 12px;
    font-weight: 600;
    cursor: pointer;
    transition: all 0.15s;
  }
  .think-opt.active-fast {
    background: var(--accent);
    color: #fff;
  }
  .think-opt.active-deep {
    background: #6366f1;
    color: #fff;
    box-shadow: 0 0 8px rgba(99,102,241,0.5);
  }
  .pill.deep-active {
    border-color: #6366f1;
    color: #c7d2fe;
  }

  .chat-container {
    flex: 1;
    overflow-y: auto;
    padding: 24px 18%;
    display: flex;
    flex-direction: column;
    gap: 18px;
  }
  @media (max-width: 1100px) {
    .chat-container { padding: 20px 6%; }
  }
  .empty-state {
    margin: auto;
    text-align: center;
    max-width: 560px;
    padding: 32px;
    background: var(--bg-card);
    border: 1px solid var(--border);
    border-radius: 14px;
  }
  .empty-state h2 { font-size: 20px; margin-bottom: 10px; color: #fff; }
  .empty-state p { font-size: 13.5px; color: var(--text-secondary); line-height: 1.6; margin-bottom: 16px; }
  .quick-prompts {
    display: grid;
    grid-template-columns: 1fr 1fr;
    gap: 8px;
    text-align: left;
  }
  .prompt-card {
    padding: 10px 12px;
    background: var(--bg-input);
    border: 1px solid var(--border);
    border-radius: 8px;
    font-size: 12.5px;
    color: var(--text-primary);
    cursor: pointer;
  }
  .prompt-card:hover { border-color: var(--accent); }

  .msg-row {
    display: flex;
    flex-direction: column;
    gap: 4px;
  }
  .msg-row.user { align-items: flex-end; }
  .msg-row.assistant { align-items: flex-start; }
  .msg-bubble {
    max-width: 85%;
    padding: 13px 16px;
    border-radius: 12px;
    font-size: 14.5px;
    line-height: 1.6;
    white-space: pre-wrap;
    word-wrap: break-word;
  }
  .msg-row.user .msg-bubble {
    background: var(--bg-user);
    color: #fff;
    border-bottom-right-radius: 3px;
  }
  .msg-row.assistant .msg-bubble {
    background: var(--bg-ai);
    border: 1px solid var(--border);
    color: var(--text-primary);
    border-bottom-left-radius: 3px;
  }
  .msg-meta {
    font-size: 11px;
    color: var(--text-secondary);
    padding: 0 4px;
  }
  .msg-bubble code {
    font-family: Consolas, monospace;
    background: rgba(0,0,0,0.35);
    padding: 2px 5px;
    border-radius: 4px;
    font-size: 13px;
  }
  .msg-bubble pre {
    background: #0b0d12;
    border: 1px solid var(--border);
    padding: 12px;
    border-radius: 8px;
    overflow-x: auto;
    margin: 8px 0;
  }

  /* ALT MESAJ GİRİŞ ALANI */
  .composer {
    padding: 14px 18%;
    background: var(--bg-sidebar);
    border-top: 1px solid var(--border);
  }
  @media (max-width: 1100px) {
    .composer { padding: 12px 6%; }
  }
  .composer-box {
    display: flex;
    gap: 10px;
    background: var(--bg-input);
    border: 1px solid var(--border);
    border-radius: 10px;
    padding: 8px 12px;
    align-items: flex-end;
  }
  .composer-box textarea {
    flex: 1;
    background: transparent;
    border: none;
    color: var(--text-primary);
    font-family: inherit;
    font-size: 14.5px;
    resize: none;
    max-height: 150px;
    min-height: 26px;
    outline: none;
    line-height: 1.45;
  }
  .btn-send {
    padding: 8px 16px;
    background: var(--accent);
    color: #fff;
    border: none;
    border-radius: 7px;
    font-weight: 600;
    font-size: 13.5px;
    cursor: pointer;
  }
  .btn-send:hover { background: var(--accent-hover); }
  .btn-stop-gen {
    padding: 8px 14px;
    background: var(--danger);
    color: #fff;
    border: none;
    border-radius: 7px;
    font-weight: 600;
    font-size: 13px;
    cursor: pointer;
    display: none;
  }
  .composer-hint {
    font-size: 11.5px;
    color: var(--text-secondary);
    text-align: center;
    margin-top: 7px;
  }
  .toast {
    position: fixed;
    bottom: 22px;
    right: 22px;
    background: #1e293b;
    border: 1px solid var(--accent);
    color: #fff;
    padding: 10px 16px;
    border-radius: 8px;
    font-size: 13px;
    display: none;
    z-index: 9999;
    box-shadow: 0 6px 20px rgba(0,0,0,0.45);
  }
</style>
</head>
<body>

<aside class="sidebar">
  <div class="sidebar-header">
    <div class="brand">
      <span class="brand-dot"></span>
      <span>Kişisel Offline AI</span>
    </div>
    <button class="btn-new-chat" onclick="createNewChat()">+ Yeni Sohbet Oluştur</button>
  </div>
  <div class="search-box">
    <input type="text" id="searchInput" placeholder="Sohbet geçmişinde ara..." oninput="renderConversationList()">
  </div>
  <div class="conv-list" id="convList"></div>
  <div class="sidebar-footer">
    <div id="dbInfoText">Yerel DB: Yükleniyor...</div>
    <div class="footer-btns">
      <button class="btn-small" onclick="backupChats()">Sohbeti Yedekle</button>
      <button class="btn-small danger" onclick="gracefulAppExit()">Uygulamayı Kapat</button>
    </div>
  </div>
</aside>

<main class="main">
  <header class="topbar">
    <div class="status-pills">
      <div class="pill" title="Yalnızca 127.0.0.1 üzerinde çalışır, dış ağa kapalıdır">
        <span class="dot on" id="ollamaDot"></span>
        <span id="ollamaStateText">Ollama: Kontrol ediliyor...</span>
      </div>
      <div class="pill" title="AMD Radeon RX 7600 ROCm GPU ve Bellek Durumu">
        <span class="dot idle" id="modelDot"></span>
        <span id="modelStateText">Model: Kontrol ediliyor...</span>
      </div>
      <div class="pill">
        <span id="memStateText">VRAM: 0 MB | RAM: 0 MB</span>
      </div>
      <div class="pill" id="thinkModePill" title="Yeni gönderilecek mesajlar için aktif düşünme modu">
        <span id="thinkModeBadge">⚡ Mod: Hızlı Mod (think: false)</span>
      </div>
    </div>
    <div class="control-bar">
      <div class="think-toggle" title="Düşünme Modu Seçimi (Yalnızca yeni gönderilecek mesajları etkiler)">
        <button id="btnFastMode" class="think-opt active-fast" onclick="setThinkMode(false)" title="Günlük sohbet ve basit sorular için (think: false)">
          ⚡ Hızlı Mod
        </button>
        <button id="btnDeepMode" class="think-opt" onclick="setThinkMode(true)" title="Matematik, mantık, programlama ve çok adımlı analiz için (think: true)">
          🧠 Derin Düşünme
        </button>
      </div>
      <select id="modelSelect" class="ctrl-btn" onchange="changeActiveModel(this.value)" title="Kullanılacak Yerel Qwen Modelini Seçin">
        <option value="qwen3:8b">Model: Qwen3 8B (Q4_K_M - En Yüksek Kalite)</option>
        <option value="qwen2.5:7b-instruct-q4_K_M">Model: Qwen 2.5 7B Instruct (Q4_K_M - Hafif/Hızlı)</option>
      </select>
      <button class="ctrl-btn start" onclick="startAI()">AI'yi Başlat</button>
      <button class="ctrl-btn unload" onclick="unloadModelOnly()">Modeli Bellekten Kaldır</button>
      <button class="ctrl-btn stop" onclick="stopAICompletely()">AI'yi Tamamen Durdur</button>
    </div>
  </header>

  <section class="chat-container" id="chatContainer"></section>

  <footer class="composer">
    <div class="composer-box">
      <textarea id="msgInput" rows="1" placeholder="Mesajınızı yazın (Enter = Gönder, Shift+Enter = Yeni satır)..." onkeydown="handleKey(event)"></textarea>
      <button class="btn-stop-gen" id="btnStopGen" onclick="stopGeneration()">Üretimi Durdur</button>
      <button class="btn-send" id="btnSend" onclick="sendMessage()">Gönder</button>
    </div>
    <div class="composer-hint">
      🔒 %100 Yerel & Çevrimdışı (127.0.0.1) | Model: <b>qwen3:8b (Q4_K_M)</b> | <span id="composerModeText">Aktif Mod: <b>⚡ Hızlı Mod (think: false)</b></span> | Pencere kapatıldığında model bellekten otomatik kaldırılır.
    </div>
  </footer>
</main>

<div class="toast" id="toastBox"></div>

<script>
let conversations = [];
let currentConvId = null;
let isGenerating = false;
let currentThinkMode = false; // Varsayılan her zaman Hızlı Mod (think: false)

function setThinkMode(enableDeep) {
  currentThinkMode = Boolean(enableDeep);
  const btnFast = document.getElementById('btnFastMode');
  const btnDeep = document.getElementById('btnDeepMode');
  const badge = document.getElementById('thinkModeBadge');
  const pill = document.getElementById('thinkModePill');
  const compTxt = document.getElementById('composerModeText');

  if (currentThinkMode) {
    btnFast.className = 'think-opt';
    btnDeep.className = 'think-opt active-deep';
    badge.textContent = '🧠 Mod: Derin Düşünme (think: true)';
    pill.className = 'pill deep-active';
    compTxt.innerHTML = 'Aktif Mod: <b>🧠 Derin Düşünme (think: true — Matematik/Mantık/Analiz)</b>';
    showToast('🧠 Derin Düşünme modu seçildi (think: true). Yeni gönderilecek mesajlarda çok adımlı çıkarım uygulanacak.');
  } else {
    btnFast.className = 'think-opt active-fast';
    btnDeep.className = 'think-opt';
    badge.textContent = '⚡ Mod: Hızlı Mod (think: false)';
    pill.className = 'pill';
    compTxt.innerHTML = 'Aktif Mod: <b>⚡ Hızlı Mod (think: false — Günlük Sohbet/Basit Sorular)</b>';
    showToast('⚡ Hızlı Mod seçildi (think: false). Yeni gönderilecek mesajlara doğrudan hızlı yanıt verilecek.');
  }
}

function showToast(msg, duration=3500) {
  const t = document.getElementById('toastBox');
  t.textContent = msg;
  t.style.display = 'block';
  setTimeout(() => { t.style.display = 'none'; }, duration);
}

function escapeHtml(str) {
  return (str || '').replace(/&/g, "&amp;").replace(/</g, "&lt;").replace(/>/g, "&gt;");
}

function formatMessageContent(text) {
  let safe = escapeHtml(text);
  safe = safe.replace(/```([a-zA-Z0-9_-]*)\n([\s\S]*?)```/g, '<pre><code>$2</code></pre>');
  safe = safe.replace(/`([^`]+)`/g, '<code>$1</code>');
  safe = safe.replace(/\*\*([^*]+)\*\*/g, '<strong>$1</strong>');
  return safe;
}

async function fetchStatus() {
  try {
    const res = await fetch('/api/status');
    const st = await res.json();
    const oDot = document.getElementById('ollamaDot');
    const oTxt = document.getElementById('ollamaStateText');
    const mDot = document.getElementById('modelDot');
    const mTxt = document.getElementById('modelStateText');
    const memTxt = document.getElementById('memStateText');
    const dbTxt = document.getElementById('dbInfoText');

    if (st.ollama_online) {
      oDot.className = 'dot on';
      oTxt.textContent = 'Servis: Aktif (127.0.0.1:11434)';
    } else {
      oDot.className = 'dot off';
      oTxt.textContent = 'Servis: Kapalı (0 MB)';
    }

    if (st.model_loaded && st.loaded_models.length > 0) {
      const lm = st.loaded_models[0];
      mDot.className = 'dot on';
      mTxt.textContent = `Bellekte: ${lm.name} (${lm.processor})`;
    } else {
      mDot.className = 'dot idle';
      mTxt.textContent = 'Model: Bellekten Kaldırıldı (0 MB VRAM)';
    }

    memTxt.textContent = `VRAM: ${st.vram_used_mb} MB | Ollama RAM: ${st.ollama_ram_mb} MB`;
    if (st.db_stats) {
      dbTxt.textContent = `Yerel DB: ${st.db_stats.conversations_count} sohbet, ${st.db_stats.messages_count} mesaj (${st.db_stats.db_size_kb} KB)`;
    }
  } catch (e) {}
}

async function loadConversations() {
  const res = await fetch('/api/conversations');
  conversations = await res.json();
  renderConversationList();
  if (!currentConvId && conversations.length > 0) {
    await selectConversation(conversations[0].id);
  } else if (conversations.length === 0) {
    renderEmptyState();
  }
}

function renderConversationList() {
  const q = (document.getElementById('searchInput').value || '').toLowerCase();
  const listEl = document.getElementById('convList');
  listEl.innerHTML = '';
  const filtered = conversations.filter(c => (c.title || '').toLowerCase().includes(q));
  filtered.forEach(c => {
    const item = document.createElement('div');
    item.className = 'conv-item' + (c.id === currentConvId ? ' active' : '');
    item.onclick = () => selectConversation(c.id);

    const titleSpan = document.createElement('span');
    titleSpan.className = 'conv-title';
    titleSpan.textContent = c.title || 'Yeni Sohbet';

    const acts = document.createElement('div');
    acts.className = 'conv-actions';

    const renBtn = document.createElement('button');
    renBtn.className = 'icon-btn';
    renBtn.title = 'Adını Değiştir';
    renBtn.textContent = '✎';
    renBtn.onclick = (ev) => { ev.stopPropagation(); renameChat(c.id, c.title); };

    const delBtn = document.createElement('button');
    delBtn.className = 'icon-btn';
    delBtn.title = 'Sohbeti Sil';
    delBtn.textContent = '🗑';
    delBtn.onclick = (ev) => { ev.stopPropagation(); deleteChat(c.id, c.title); };

    acts.appendChild(renBtn);
    acts.appendChild(delBtn);
    item.appendChild(titleSpan);
    item.appendChild(acts);
    listEl.appendChild(item);
  });
}

function renderEmptyState() {
  const box = document.getElementById('chatContainer');
  box.innerHTML = `
    <div class="empty-state">
      <h2>Kişisel Offline AI Sistemine Hoş Geldiniz</h2>
      <p>
        Tüm sorularınız internet bağlantısı olmadan, doğrudan bilgisayarınızdaki
        <b>AMD Radeon RX 7600 (8 GB VRAM)</b> ekran kartı üzerinde çalışan
        <b>Qwen3 8B (4-bit Q4_K_M Instruct)</b> modeli tarafından yanıtlanır.
        Hiçbir veri bilgisayarınızdan dışarı çıkmaz.
      </p>
      <div class="quick-prompts">
        <div class="prompt-card" onclick="useQuickPrompt('Bana kuantum bilgisayarların çalışma mantığını sade ve anlaşılır bir Türkçeyle açıklar mısın?')">
          💡 Kuantum bilgisayarları sade Türkçeyle açıkla
        </div>
        <div class="prompt-card" onclick="useQuickPrompt('Bir odada 3 lamba, dışarıda 3 anahtar var. Odaya sadece 1 kez girerek hangi anahtarın hangi lambayı yaktığını nasıl bulurum?')">
          🧠 3 lamba ve 3 anahtar mantık sorusunu çöz
        </div>
        <div class="prompt-card" onclick="useQuickPrompt('Yoğun bir iş gününü verimli planlamak için 5 maddelik pratik bir zaman yönetimi listesi hazırla.')">
          📋 Günlük zaman yönetimi planı oluştur
        </div>
        <div class="prompt-card" onclick="useQuickPrompt('Python ile yerel bir klasördeki dosyaları uzantılarına göre düzenleyen örnek bir betik yaz.')">
          💻 Python dosya düzenleme betiği yaz
        </div>
      </div>
    </div>
  `;
}

function useQuickPrompt(text) {
  document.getElementById('msgInput').value = text;
  sendMessage();
}

async function createNewChat() {
  const res = await fetch('/api/conversations', { method: 'POST' });
  const conv = await res.json();
  currentConvId = conv.id;
  await loadConversations();
  await selectConversation(conv.id);
}

async function selectConversation(id) {
  currentConvId = id;
  renderConversationList();
  const res = await fetch(`/api/conversations/${id}`);
  if (!res.ok) return;
  const conv = await res.json();
  const box = document.getElementById('chatContainer');
  box.innerHTML = '';
  if (!conv.messages || conv.messages.length === 0) {
    renderEmptyState();
    return;
  }
  conv.messages.forEach(m => appendMessageDom(m.role, m.content, m.created_at, m.metrics_json));
  box.scrollTop = box.scrollHeight;
}

function appendMessageDom(role, content, createdAt='', metricsJson='{}') {
  const box = document.getElementById('chatContainer');
  const empty = box.querySelector('.empty-state');
  if (empty) empty.remove();

  const row = document.createElement('div');
  row.className = 'msg-row ' + role;

  const bubble = document.createElement('div');
  bubble.className = 'msg-bubble';
  bubble.innerHTML = formatMessageContent(content);

  const meta = document.createElement('div');
  meta.className = 'msg-meta';
  let metaText = role === 'user' ? 'Siz' : 'Qwen3 8B (Yerel)';
  if (createdAt) metaText += ' • ' + createdAt.replace('T', ' ');
  try {
    const m = typeof metricsJson === 'string' ? JSON.parse(metricsJson || '{}') : (metricsJson || {});
    if (m.mode_label) {
      metaText += m.think_mode ? ` • 🧠 ${m.mode_label}` : ` • ⚡ ${m.mode_label}`;
    }
    if (m.tokens_per_sec) {
      metaText += ` • ${m.tokens_per_sec} token/sn (${m.eval_count} token)`;
    }
  } catch (e) {}
  meta.textContent = metaText;

  row.appendChild(bubble);
  row.appendChild(meta);
  box.appendChild(row);
  box.scrollTop = box.scrollHeight;
  return { row, bubble, meta };
}

function handleKey(e) {
  if (e.key === 'Enter' && !e.shiftKey) {
    e.preventDefault();
    sendMessage();
  }
}

async function sendMessage() {
  if (isGenerating) return;
  const input = document.getElementById('msgInput');
  const text = input.value.trim();
  if (!text) return;
  input.value = '';

  if (!currentConvId) {
    const res = await fetch('/api/conversations', { method: 'POST' });
    const conv = await res.json();
    currentConvId = conv.id;
  }

  const sentWithThink = currentThinkMode;
  appendMessageDom('user', text);
  const aiDom = appendMessageDom('assistant', sentWithThink ? '🧠 Derin düşünülüyor...' : '...');
  isGenerating = true;
  document.getElementById('btnSend').style.display = 'none';
  document.getElementById('btnStopGen').style.display = 'inline-block';

  let accumulated = '';
  try {
    const response = await fetch('/api/chat', {
      method: 'POST',
      headers: { 'Content-Type': 'application/json' },
      body: JSON.stringify({ conversation_id: currentConvId, message: text, think: sentWithThink })
    });

    const reader = response.body.getReader();
    const decoder = new TextDecoder('utf-8');
    let buffer = '';

    while (true) {
      const { value, done } = await reader.read();
      if (done) break;
      buffer += decoder.decode(value, { stream: true });
      const lines = buffer.split('\n');
      buffer = lines.pop();
      for (const line of lines) {
        if (!line.trim()) continue;
        const evt = JSON.parse(line);
        if (evt.type === 'thinking') {
          if (!accumulated) {
            aiDom.bubble.innerHTML = `<em>🧠 Derin düşünülüyor... (${evt.thinking_chars || 0} karakter içsel analiz)</em>`;
          }
        } else if (evt.type === 'chunk' || evt.type === 'error') {
          accumulated += evt.content;
          aiDom.bubble.innerHTML = formatMessageContent(accumulated);
          const box = document.getElementById('chatContainer');
          box.scrollTop = box.scrollHeight;
        } else if (evt.type === 'done') {
          if (evt.metrics && evt.metrics.tokens_per_sec) {
            const modeIcon = evt.metrics.think_mode ? '🧠 Derin Düşünme' : '⚡ Hızlı Mod';
            aiDom.meta.textContent = `Qwen3 8B (Yerel) • ${modeIcon} • ${evt.metrics.tokens_per_sec} token/sn (${evt.metrics.eval_count} token, ${evt.metrics.total_duration_s} sn)`;
          }
        }
      }
    }
  } catch (err) {
    aiDom.bubble.innerHTML = formatMessageContent(accumulated + '\n[İstek durduruldu veya bağlantı kesildi]');
  } finally {
    isGenerating = false;
    document.getElementById('btnSend').style.display = 'inline-block';
    document.getElementById('btnStopGen').style.display = 'none';
    await loadConversations();
    await fetchStatus();
  }
}

async function stopGeneration() {
  await fetch('/api/lifecycle/stop_generation', { method: 'POST' });
  showToast('Üretim güvenli şekilde durduruldu.');
}

async function changeActiveModel(modelName) {
  await fetch('/api/lifecycle/set_model', {
    method: 'POST',
    headers: { 'Content-Type': 'application/json' },
    body: JSON.stringify({ model: modelName })
  });
  showToast(`Aktif model değiştirildi: ${modelName}`);
  await fetchStatus();
}

async function startAI() {
  showToast('Ollama servisi başlatılıyor ve model RX 7600 GPU belleğine yükleniyor...');
  const res = await fetch('/api/lifecycle/start', { method: 'POST' });
  const data = await res.json();
  await fetchStatus();
  showToast('AI Servisi ve Model hazır! (%100 GPU)');
}

async function unloadModelOnly() {
  showToast('Model GPU VRAM belleğinden kaldırılıyor (ollama stop)...');
  const res = await fetch('/api/lifecycle/unload', { method: 'POST' });
  const data = await res.json();
  await fetchStatus();
  showToast(`Model bellekten kaldırıldı! Serbest bırakılan VRAM: ${data.vram_freed_mb} MB`);
}

async function stopAICompletely() {
  showToast('AI üretimi, model ve Ollama arka plan servisi tamamen durduruluyor...');
  const res = await fetch('/api/lifecycle/stop_all', { method: 'POST' });
  const data = await res.json();
  await fetchStatus();
  showToast('AI tamamen durduruldu. Bilgisayar kaynakları serbest bırakıldı.');
}

async function backupChats() {
  const res = await fetch('/api/backup', { method: 'POST' });
  const data = await res.json();
  showToast(`Yedek oluşturuldu: ${data.backup_path} (${data.size_kb} KB)`, 5000);
}

async function renameChat(id, oldTitle) {
  const newTitle = prompt('Sohbet için yeni başlık girin:', oldTitle || '');
  if (!newTitle || !newTitle.trim()) return;
  await fetch(`/api/conversations/${id}/rename`, {
    method: 'POST',
    headers: { 'Content-Type': 'application/json' },
    body: JSON.stringify({ title: newTitle.trim() })
  });
  await loadConversations();
}

async function deleteChat(id, title) {
  if (!confirm(`"${title}" başlıklı sohbeti silmek istediğinize emin misiniz?`)) return;
  await fetch(`/api/conversations/${id}`, { method: 'DELETE' });
  if (currentConvId === id) currentConvId = null;
  await loadConversations();
  await fetchStatus();
}

async function gracefulAppExit() {
  showToast('Uygulama kapatılıyor: Model bellekten kaldırılıyor ve Ollama durduruluyor...');
  await fetch('/api/lifecycle/exit_app', { method: 'POST' });
}

setInterval(fetchStatus, 2500);
window.addEventListener('DOMContentLoaded', async () => {
  await fetchStatus();
  await loadConversations();
});
</script>
</body>
</html>
"""


class ThreadedHTTPServer(socketserver.ThreadingMixIn, http.server.HTTPServer):
    daemon_threads = True
    allow_reuse_address = True


class LocalAIRequestHandler(http.server.BaseHTTPRequestHandler):
    def log_message(self, format, *args):
        pass

    def _send_json(self, obj, status=200):
        body = json.dumps(obj, ensure_ascii=False).encode("utf-8")
        self.send_response(status)
        self.send_header("Content-Type", "application/json; charset=utf-8")
        self.send_header("Cache-Control", "no-store")
        self.send_header("Content-Length", str(len(body)))
        self.end_headers()
        self.wfile.write(body)

    def _read_json(self) -> dict:
        length = int(self.headers.get("Content-Length", 0))
        if length <= 0:
            return {}
        return json.loads(self.rfile.read(length).decode("utf-8"))

    def do_GET(self):
        parsed = urllib.parse.urlparse(self.path)
        path = parsed.path

        if path == "/" or path == "/index.html":
            body = HTML_UI.encode("utf-8")
            self.send_response(200)
            self.send_header("Content-Type", "text/html; charset=utf-8")
            self.send_header("Cache-Control", "no-store")
            self.send_header("Content-Length", str(len(body)))
            self.end_headers()
            self.wfile.write(body)
            return

        if path == "/api/status":
            self._send_json(manager.get_status())
            return

        if path == "/api/conversations":
            self._send_json(db.list_conversations())
            return

        if path.startswith("/api/conversations/"):
            conv_id = path.split("/api/conversations/")[1].strip("/")
            conv = db.get_conversation(conv_id)
            if not conv:
                self._send_json({"error": "Bulunamadı"}, status=404)
            else:
                self._send_json(conv)
            return

        self._send_json({"error": "Not found"}, status=404)

    def do_POST(self):
        parsed = urllib.parse.urlparse(self.path)
        path = parsed.path

        if path == "/api/conversations":
            conv = db.create_conversation()
            self._send_json(conv)
            return

        if path.startswith("/api/conversations/") and path.endswith("/rename"):
            conv_id = path.split("/api/conversations/")[1].split("/rename")[0]
            data = self._read_json()
            ok = db.rename_conversation(conv_id, data.get("title", "Sohbet"))
            self._send_json({"ok": ok})
            return

        if path == "/api/backup":
            info = db.create_backup(tag="ui")
            self._send_json(info)
            return

        if path == "/api/lifecycle/set_model":
            data = self._read_json()
            st = manager.set_active_model(data.get("model", DEFAULT_MODEL))
            self._send_json(st)
            return

        if path == "/api/lifecycle/start":
            st = manager.start_ollama(preload_model=True)
            self._send_json(st)
            return

        if path == "/api/lifecycle/unload":
            res = manager.unload_model()
            self._send_json(res)
            return

        if path == "/api/lifecycle/stop_generation":
            manager.cancel_active_generation()
            self._send_json({"stopped": True})
            return

        if path == "/api/lifecycle/stop_all":
            res = manager.execute_ordered_shutdown(trigger_source="STOP_AI_BUTTON")
            self._send_json(res)
            return

        if path == "/api/lifecycle/exit_app":
            self._send_json({"exiting": True})
            threading.Thread(target=trigger_full_app_shutdown, args=("NORMAL_EXIT",), daemon=True).start()
            return

        if path == "/api/chat":
            data = self._read_json()
            conv_id = data.get("conversation_id")
            message = data.get("message", "")
            use_think = bool(data.get("think", False))
            self.send_response(200)
            self.send_header("Content-Type", "application/x-ndjson; charset=utf-8")
            self.send_header("Cache-Control", "no-store")
            self.end_headers()
            try:
                for event in manager.stream_chat(conv_id, message, think=use_think):
                    line = (json.dumps(event, ensure_ascii=False) + "\n").encode("utf-8")
                    self.wfile.write(line)
                    self.wfile.flush()
            except Exception:
                pass
            return

        self._send_json({"error": "Not found"}, status=404)

    def do_DELETE(self):
        parsed = urllib.parse.urlparse(self.path)
        path = parsed.path
        if path.startswith("/api/conversations/"):
            conv_id = path.split("/api/conversations/")[1].strip("/")
            ok = db.delete_conversation(conv_id)
            self._send_json({"ok": ok})
            return
        self._send_json({"error": "Not found"}, status=404)


def create_tray_image() -> Image.Image:
    """Windows sistem tepsisi (sağ alt köşe) için özel simge oluşturur."""
    img = Image.new("RGBA", (64, 64), (15, 17, 23, 255))
    draw = ImageDraw.Draw(img)
    draw.rounded_rectangle((4, 4, 60, 60), radius=14, fill=(16, 163, 127, 255), outline=(255, 255, 255, 220), width=2)
    draw.ellipse((18, 18, 46, 46), fill=(15, 17, 23, 255))
    draw.ellipse((26, 26, 38, 38), fill=(16, 163, 127, 255))
    return img


def trigger_full_app_shutdown(reason: str):
    """
    Hem X butonu, hem Sistem Tepsisi (Quit / Exit), hem de Normal Çıkış tarafından
    çağrılan birleşik kapatma yöneticisi.
    """
    if _app_exiting.is_set():
        return
    _app_exiting.set()

    # 5 Aşamalı Sıralı Kapatmayı Çalıştır
    manager.execute_ordered_shutdown(trigger_source=reason)

    # Sistem tepsisi simgesini kapat
    global _tray_icon, _webview_window, _http_server
    if _tray_icon is not None:
        try:
            _tray_icon.stop()
        except Exception:
            pass

    # Pencere açık ise kapat
    if _webview_window is not None and reason != "X_BUTTON":
        try:
            _webview_window.destroy()
        except Exception:
            pass

    # Yerel HTTP sunucusunu kapat
    if _http_server is not None:
        try:
            _http_server.shutdown()
        except Exception:
            pass


def on_tray_show_window(icon, item):
    if _webview_window is not None:
        try:
            _webview_window.show()
            _webview_window.restore()
        except Exception:
            pass


def on_tray_unload_model(icon, item):
    threading.Thread(target=manager.unload_model, daemon=True).start()


def on_tray_quit(icon, item):
    """Sistem tepsisinden sağ tıklayıp Quit / Exit seçildiğinde çalışır."""
    logger.info("Sistem tepsisi menüsünden 'Quit / Exit' seçildi.")
    threading.Thread(target=trigger_full_app_shutdown, args=("TRAY_QUIT",), daemon=True).start()


def setup_system_tray():
    global _tray_icon
    menu = pystray.Menu(
        pystray.MenuItem("Sohbet Penceresini Göster", on_tray_show_window, default=True),
        pystray.MenuItem("Modeli Bellekten Kaldır (ollama stop)", on_tray_unload_model),
        pystray.Menu.SEPARATOR,
        pystray.MenuItem("Quit / Exit", on_tray_quit),
    )
    _tray_icon = pystray.Icon(
        "KisiselOfflineAI",
        create_tray_image(),
        "Kişisel Offline AI (Qwen3 8B - Yerel)",
        menu,
    )
    _tray_icon.run_detached()
    logger.info("Windows Sistem Tepsisi (System Tray) simgesi aktif edildi (Quit / Exit menüsü hazır).")


def on_window_closing():
    """Sohbet penceresinin sağ üstündeki X butonuna basıldığında tetiklenir."""
    if not _app_exiting.is_set():
        logger.info("Pencere sağ üst X butonuna basıldı (WM_CLOSE) -> Otomatik kapatma başlatılıyor.")
        trigger_full_app_shutdown("X_BUTTON")
    return True


def run_application(auto_test_mode: str = None, preload_on_start: bool = False):
    global _webview_window, _http_server

    logger.info("=" * 72)
    logger.info(f"UYGULAMA BAŞLATILIYOR | auto_test_mode={auto_test_mode}")

    # 1. Uygulama açıldığında Ollama servisini otomatik başlat
    manager.start_ollama(preload_model=preload_on_start)

    # 2. Yerel HTTP Arayüz Sunucusunu yalnızca 127.0.0.1 üzerinde başlat
    _http_server = ThreadedHTTPServer((APP_HOST, APP_PORT), LocalAIRequestHandler)
    server_thread = threading.Thread(target=_http_server.serve_forever, daemon=True)
    server_thread.start()
    logger.info(f"Yerel Web Arayüzü dinlemede: http://{APP_HOST}:{APP_PORT}")

    # 3. Windows Sistem Tepsisi (System Tray) simgesini başlat
    setup_system_tray()

    # 4. Masaüstü Sohbet Penceresini oluştur
    _webview_window = webview.create_window(
        "Kişisel Offline AI — Qwen3 8B (4-Bit Q4_K_M | Yerel & Gizli)",
        f"http://{APP_HOST}:{APP_PORT}",
        width=1240,
        height=820,
        min_size=(900, 600),
        background_color="#0f1117",
    )
    _webview_window.events.closing += on_window_closing

    # Otomatik test modları: X butonu veya Sistem Tepsisi Quit davranışını gerçek süreçte doğrular
    if auto_test_mode in ("x_button", "tray_quit"):
        def _auto_test_worker():
            time.sleep(3.0)
            logger.info(f"[AUTO-TEST] Test için model GPU belleğine yükleniyor ({DEFAULT_MODEL})...")
            manager.preload_model()
            loaded = manager.get_loaded_models()
            logger.info(f"[AUTO-TEST] Kapatma öncesi bellekteki model durumu: {loaded}")
            time.sleep(1.5)
            if auto_test_mode == "x_button":
                logger.info("[AUTO-TEST] Sağ üst X butonu (pencere kapatma olayı) tetikleniyor...")
                _webview_window.destroy()
            elif auto_test_mode == "tray_quit":
                logger.info("[AUTO-TEST] Sistem Tepsisi (System Tray) 'Quit / Exit' menü öğesi tetikleniyor...")
                on_tray_quit(_tray_icon, None)

        threading.Thread(target=_auto_test_worker, daemon=True).start()

    webview.start()
    # Webview ana döngüsü bittiğinde hala kapanmadıysa güvenli kapatmayı tamamla
    if not _app_exiting.is_set():
        trigger_full_app_shutdown("X_BUTTON")


if __name__ == "__main__":
    parser = argparse.ArgumentParser(description="Kişisel Offline AI Masaüstü Uygulaması")
    parser.add_argument("--test-x-close", action="store_true", help="Pencere X butonu ile kapatma testini çalıştır")
    parser.add_argument("--test-tray-quit", action="store_true", help="Sistem tepsisi Quit/Exit ile kapatma testini çalıştır")
    parser.add_argument("--preload", action="store_true", help="Başlangıçta modeli GPU belleğine önceden yükle")
    args = parser.parse_args()

    mode = None
    if args.test_x_close:
        mode = "x_button"
    elif args.test_tray_quit:
        mode = "tray_quit"

    run_application(auto_test_mode=mode, preload_on_start=args.preload)
