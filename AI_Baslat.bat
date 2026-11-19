@echo off
chcp 65001 >nul
cd /d "%~dp0"
set OLLAMA_HOST=127.0.0.1:11434
set OLLAMA_ORIGINS=http://127.0.0.1:*,http://localhost:*
set OLLAMA_NO_CLOUD=1
set DO_NOT_TRACK=1
where pythonw >nul 2>nul
if %ERRORLEVEL% EQU 0 (
    start "" pythonw "%~dp0app.py"
) else (
    start "" python "%~dp0app.py"
)
