@echo off
title Servidor Lunia - Activo
cd /d "c:\Users\diana\OneDrive\Documentos\Lunia"
:: Usamos el entorno virtual para asegurar que las librerias carguen
call .\venv\Scripts\activate
python main.py
pause
