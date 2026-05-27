@echo off
cd /d "%~dp0frontend"
echo [FRONTEND] Instaluji npm zavislosti...
npm install
echo [FRONTEND] Spoustim Vite dev server na http://localhost:5173
npm run dev
