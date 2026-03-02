#!/bin/bash
# stock-signal-platform unified launcher
# Usage: ./run.sh start | stop | status | restart

set -e

RED='\033[0;31m'
GREEN='\033[0;32m'
YELLOW='\033[1;33m'
NC='\033[0m'

case "$1" in
  start)
    mkdir -p .pids
    echo -e "${GREEN}Starting infrastructure...${NC}"
    docker compose up -d postgres redis
    echo "Waiting for Postgres..."
    sleep 3

    echo -e "${GREEN}Running migrations...${NC}"
    uv run alembic upgrade head

    echo -e "${GREEN}Starting backend (port 8181)...${NC}"
    uv run uvicorn backend.main:app --reload --port 8181 &
    echo $! > .pids/backend.pid

    if [ -d "frontend/node_modules" ]; then
      echo -e "${GREEN}Starting frontend (port 3000)...${NC}"
      cd frontend && npm run dev &
      echo $! > ../.pids/frontend.pid
      cd ..
    else
      echo -e "${YELLOW}Frontend not installed yet. Run: cd frontend && npm install${NC}"
    fi

    echo -e "${GREEN}All services started.${NC}"
    ;;

  stop)
    echo -e "${YELLOW}Stopping services...${NC}"
    [ -f .pids/backend.pid ] && kill "$(cat .pids/backend.pid)" 2>/dev/null && rm .pids/backend.pid
    [ -f .pids/frontend.pid ] && kill "$(cat .pids/frontend.pid)" 2>/dev/null && rm .pids/frontend.pid
    docker compose down
    echo -e "${GREEN}All services stopped.${NC}"
    ;;

  status)
    echo "=== Docker ==="
    docker compose ps
    echo ""
    echo "=== Backend ==="
    if [ -f .pids/backend.pid ] && kill -0 "$(cat .pids/backend.pid)" 2>/dev/null; then
      echo -e "${GREEN}Running (PID $(cat .pids/backend.pid))${NC}"
    else
      echo -e "${RED}Not running${NC}"
    fi
    echo ""
    echo "=== Frontend ==="
    if [ -f .pids/frontend.pid ] && kill -0 "$(cat .pids/frontend.pid)" 2>/dev/null; then
      echo -e "${GREEN}Running (PID $(cat .pids/frontend.pid))${NC}"
    else
      echo -e "${RED}Not running${NC}"
    fi
    ;;

  restart)
    $0 stop
    sleep 2
    $0 start
    ;;

  *)
    echo "Usage: $0 {start|stop|status|restart}"
    exit 1
    ;;
esac
