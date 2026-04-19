@echo off
setlocal
set PATH=%PATH%;C:\Program Files\nodejs

echo 🚀 Starting VI Portfolio (Modern Refactor)
echo.

:: Start Backend
echo [1/2] Starting Python API (FastAPI)...
start "VI Portfolio API" cmd /c ".\.venv\Scripts\python.exe api\main.py"

:: Wait for backend to warm up
timeout /t 3 /nobreak > nul

:: Start Frontend
echo [2/2] Starting Frontend (Vite)...
cd frontend
start "VI Portfolio UI" cmd /c "npx vite"

echo.
echo ✨ Application is starting! 
echo 👉 Backend: http://localhost:8000
echo 👉 Frontend: http://localhost:5173
echo.
echo Press any key to stop this script.
pause
