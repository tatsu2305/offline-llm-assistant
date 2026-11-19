@echo off
chcp 65001 >nul
cd /d "%~dp0"
python "%~dp0backup_chats.py"
echo.
pause
