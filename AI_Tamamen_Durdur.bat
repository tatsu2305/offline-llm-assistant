@echo off
chcp 65001 >nul
cd /d "%~dp0"
echo AI uretimi, model ve Ollama arka plan servisi tamamen durduruluyor...
python -c "from ai_manager import ChatDatabase, OllamaLifecycleManager; m = OllamaLifecycleManager(ChatDatabase()); print(m.execute_ordered_shutdown('BATCH_SCRIPT_STOP'))"
echo.
echo AI tamamen durduruldu ve bellek serbest birakildi.
pause
