@echo off
title Servidor Lunia - Activo
cd /d "%~dp0"
if exist venv\Scripts\activate (
    call venv\Scripts\activate
)
python main.py
pause
