@echo off
chcp 65001 >nul
cd /d "%~dp0"
echo Model GPU VRAM belleginden kaldiriliyor (ollama stop qwen3:8b)...
python -c "from ai_manager import ChatDatabase, OllamaLifecycleManager; m = OllamaLifecycleManager(ChatDatabase()); print(m.unload_model())"
echo.
echo Model bellekten kaldirildi.
pause
