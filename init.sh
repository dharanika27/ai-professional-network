#!/bin/bash
set -euo pipefail

echo "=== Bootstrapping dev environment ==="

# Backend dependencies
cd backend && uv sync && cd ..

# Frontend dependencies
cd frontend && npm ci && cd ..

# Environment
if [ -f ".env.example" ] && [ ! -f ".env" ]; then
  cp .env.example .env
  echo "Created .env from .env.example — add your API keys"
fi

# Start dev servers (local verification mode)
echo "Starting backend on :8000 and frontend on :3000 ..."
(cd backend && uv run uvicorn src.main:app --host 0.0.0.0 --port 8000) &
BACKEND_PID=$!
(cd frontend && npm run dev -- --port 3000) &
FRONTEND_PID=$!

# Health checks
echo "Waiting for services..."
for i in 1 2 3 4 5; do
  if curl -sf http://localhost:8000/health >/dev/null 2>&1; then
    echo "Backend healthy"
    break
  fi
  echo "  backend not ready (attempt $i/5), retrying in 2s..."
  sleep 2
done

for i in 1 2 3 4 5; do
  if curl -sf http://localhost:3000/health >/dev/null 2>&1 || curl -sf http://localhost:3000 >/dev/null 2>&1; then
    echo "Frontend healthy"
    break
  fi
  echo "  frontend not ready (attempt $i/5), retrying in 2s..."
  sleep 2
done

echo "=== Environment ready ==="
echo "Backend PID: $BACKEND_PID  |  Frontend PID: $FRONTEND_PID"
echo "Stop with: kill $BACKEND_PID $FRONTEND_PID"
wait
