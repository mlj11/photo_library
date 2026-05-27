@echo off
cd /d "%~dp0backend"
echo [BACKEND] Instaluji zavislosti...
pip install -r requirements.txt
echo [BACKEND] Spoustim FastAPI na http://localhost:8000
uvicorn main:app --reload --port 8000
