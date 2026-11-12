@echo off
cd /d "%~dp0"
echo Iniciando MangaTrack em http://localhost:8000 ...
.\.venv\Scripts\python -m uvicorn app:app --host 127.0.0.1 --port 8000 --reload
