#!/usr/bin/env bash
# One-command plug-and-play launcher.
#
#   ./start.sh            → full Docker stack (Postgres + Redis + API + worker + web)
#   ./start.sh --local    → no Docker: SQLite + in-process worker + dev servers
#   ./start.sh --stop     → stop whichever mode is running
#
# Either mode ends with the app at http://localhost:3000 (admin / admin123)
# and the API at http://localhost:8000/docs, seeded with demo data.
set -euo pipefail
cd "$(dirname "$0")"

RED=$'\033[0;31m'; GREEN=$'\033[0;32m'; YELLOW=$'\033[0;33m'; NC=$'\033[0m'
say()  { echo "${GREEN}[start]${NC} $*"; }
warn() { echo "${YELLOW}[start]${NC} $*"; }
die()  { echo "${RED}[start]${NC} $*" >&2; exit 1; }

PIDFILE=".local-stack.pids"

wait_for() { # wait_for <url> <label> [tries]
  local url=$1 label=$2 tries=${3:-60}
  for _ in $(seq 1 "$tries"); do
    if curl -fsS "$url" >/dev/null 2>&1; then say "$label is up: $url"; return 0; fi
    sleep 2
  done
  die "$label did not come up at $url"
}

stop_all() {
  if [ -f "$PIDFILE" ]; then
    warn "Stopping local processes ($(tr '\n' ' ' < "$PIDFILE"))"
    xargs -r kill < "$PIDFILE" 2>/dev/null || true
    rm -f "$PIDFILE"
  fi
  if command -v docker >/dev/null 2>&1 && docker info >/dev/null 2>&1; then
    docker compose down 2>/dev/null || true
  fi
  say "Stopped."
}

start_docker() {
  command -v docker >/dev/null 2>&1 || die "Docker is not installed. Use: ./start.sh --local"
  docker info >/dev/null 2>&1 || die "Docker daemon is not running. Start it, or use: ./start.sh --local"
  [ -f .env ] || { cp .env.example .env; say "Created .env from .env.example"; }

  say "Building and starting the full stack (this can take a few minutes on first run)…"
  docker compose up --build -d
  wait_for http://localhost:8000/health "API" 90
  say "Seeding demo data (admin + opt-out students + one processed upload)…"
  docker compose exec -T api python -m app.scripts.seed_demo
  wait_for http://localhost:3000 "Web console" 60
  say ""
  say "Ready!  Web: http://localhost:3000   API docs: http://localhost:8000/docs"
  say "Login: admin / admin123"
}

start_local() {
  command -v python3 >/dev/null 2>&1 || die "python3 is required"
  command -v node    >/dev/null 2>&1 || die "node is required"

  say "Setting up backend (venv + dependencies)…"
  if [ ! -d .venv ]; then python3 -m venv .venv; fi
  # shellcheck disable=SC1091
  source .venv/bin/activate
  pip install -q --upgrade pip
  pip install -q -r backend/requirements-dev.txt

  say "Installing verified YuNet + SFace vision models…"
  (cd backend && python -m app.scripts.download_models)

  say "Seeding demo data…"
  (cd backend && python -m app.scripts.seed_demo)

  say "Setting up frontend (npm dependencies)…"
  (cd frontend && npm install --no-audit --no-fund >/dev/null)
  [ -f frontend/.env.local ] || cp frontend/.env.local.example frontend/.env.local

  say "Starting API (http://localhost:8000) and web app (http://localhost:3000)…"
  (cd backend && ../.venv/bin/uvicorn app.main:app --host 0.0.0.0 --port 8000 >/tmp/faceblur-api.log 2>&1) &
  echo $! > "$PIDFILE"
  (cd frontend && npm run dev >/tmp/faceblur-web.log 2>&1) &
  echo $! >> "$PIDFILE"

  wait_for http://localhost:8000/health "API" 30
  wait_for http://localhost:3000 "Web console" 60
  say ""
  say "Ready!  Web: http://localhost:3000   API docs: http://localhost:8000/docs"
  say "Login: admin / admin123    Logs: /tmp/faceblur-api.log /tmp/faceblur-web.log"
  say "Stop with: ./start.sh --stop"
}

case "${1:-}" in
  --stop)  stop_all ;;
  --local) start_local ;;
  "")      start_docker ;;
  *)       die "Unknown option: $1 (use --local, --stop, or no argument for Docker)" ;;
esac
