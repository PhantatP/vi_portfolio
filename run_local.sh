#!/bin/bash
export VI_DB_PATH="$HOME/OneDrive/vi_portfolio/db/vi_portfolio.db"

echo "Starting VI Portfolio (Modern Refactor)"
echo

# Start Backend
echo "[1/2] Starting Python API (FastAPI)..."
./.venv/bin/python api/main.py &
BACKEND_PID=$!

# Wait for backend to warm up
sleep 3

# Start Frontend
echo "[2/2] Starting Frontend (Vite)..."
cd frontend && npx vite --host &
FRONTEND_PID=$!

echo
echo "Application is starting!"
echo "Backend:  http://localhost:8000"
echo "Frontend: http://localhost:5173"
echo
echo "Press Ctrl+C to stop."

trap "kill $BACKEND_PID $FRONTEND_PID 2>/dev/null; exit 0" INT TERM
wait
