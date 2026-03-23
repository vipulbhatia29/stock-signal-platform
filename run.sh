#!/bin/bash
# stock-signal-platform unified launcher
# Usage: ./run.sh start | stop | status | restart | logs [service]

set -e

RED='\033[0;31m'
GREEN='\033[0;32m'
YELLOW='\033[1;33m'
CYAN='\033[0;36m'
NC='\033[0m'

PID_DIR=".pids"
LOG_DIR="logs"

_check_pid() {
  [ -f "$PID_DIR/$1.pid" ] && kill -0 "$(cat "$PID_DIR/$1.pid")" 2>/dev/null
}

_stop_pid() {
  if [ -f "$PID_DIR/$1.pid" ]; then
    local pid
    pid=$(cat "$PID_DIR/$1.pid")
    if kill -0 "$pid" 2>/dev/null; then
      kill "$pid" 2>/dev/null
      echo -e "  ${YELLOW}Stopped $1 (PID $pid)${NC}"
    fi
    rm -f "$PID_DIR/$1.pid"
  fi
}

case "$1" in
  start)
    mkdir -p "$PID_DIR" "$LOG_DIR"

    echo -e "${GREEN}[1/6] Starting infrastructure...${NC}"
    docker compose up -d postgres redis
    echo "  Waiting for Postgres health check..."
    until docker compose exec -T postgres pg_isready -U stocksignal > /dev/null 2>&1; do
      sleep 1
    done
    echo -e "  ${GREEN}Postgres + Redis healthy${NC}"

    echo -e "${GREEN}[2/6] Running migrations...${NC}"
    uv run alembic upgrade head

    echo -e "${GREEN}[3/6] Starting backend (port 8181)...${NC}"
    uv run uvicorn backend.main:app --reload --port 8181 > "$LOG_DIR/backend.log" 2>&1 &
    echo $! > "$PID_DIR/backend.pid"
    echo -e "  PID $(cat "$PID_DIR/backend.pid")"

    if [ -d "frontend/node_modules" ]; then
      echo -e "${GREEN}[4/6] Starting frontend (port 3000)...${NC}"
      cd frontend && npm run dev > "../$LOG_DIR/frontend.log" 2>&1 &
      echo $! > "../$PID_DIR/frontend.pid"
      cd ..
      echo -e "  PID $(cat "$PID_DIR/frontend.pid")"
    else
      echo -e "${YELLOW}[4/6] Frontend not installed. Run: cd frontend && npm install${NC}"
    fi

    echo -e "${GREEN}[5/6] Starting Celery worker...${NC}"
    uv run celery -A backend.tasks worker --loglevel=info > "$LOG_DIR/celery-worker.log" 2>&1 &
    echo $! > "$PID_DIR/celery-worker.pid"
    echo -e "  PID $(cat "$PID_DIR/celery-worker.pid")"

    echo -e "${GREEN}[6/6] Starting Celery Beat scheduler...${NC}"
    uv run celery -A backend.tasks beat --loglevel=info > "$LOG_DIR/celery-beat.log" 2>&1 &
    echo $! > "$PID_DIR/celery-beat.pid"
    echo -e "  PID $(cat "$PID_DIR/celery-beat.pid")"

    echo ""
    echo -e "${GREEN}All services started.${NC}"
    echo -e "  Backend:  ${CYAN}http://localhost:8181${NC}"
    echo -e "  Frontend: ${CYAN}http://localhost:3000${NC}"
    echo -e "  Postgres: ${CYAN}localhost:5433${NC}"
    echo -e "  Redis:    ${CYAN}localhost:6380${NC}"
    echo -e "  Logs:     ${CYAN}./logs/*.log${NC}"
    ;;

  stop)
    echo -e "${YELLOW}Stopping services...${NC}"
    _stop_pid "celery-beat"
    _stop_pid "celery-worker"
    _stop_pid "frontend"
    _stop_pid "backend"
    docker compose down
    echo -e "${GREEN}All services stopped.${NC}"
    ;;

  status)
    echo -e "${CYAN}=== Docker ===${NC}"
    docker compose ps --format "table {{.Name}}\t{{.Status}}\t{{.Ports}}" 2>/dev/null || docker compose ps

    echo ""
    for svc in backend frontend celery-worker celery-beat; do
      if _check_pid "$svc"; then
        echo -e "  $svc: ${GREEN}Running (PID $(cat "$PID_DIR/$svc.pid"))${NC}"
      else
        echo -e "  $svc: ${RED}Not running${NC}"
      fi
    done
    ;;

  restart)
    $0 stop
    sleep 2
    $0 start
    ;;

  logs)
    if [ -n "$2" ]; then
      tail -f "$LOG_DIR/$2.log"
    else
      echo "Usage: $0 logs {backend|frontend|celery-worker|celery-beat}"
      echo ""
      echo "Available logs:"
      ls -1 "$LOG_DIR"/*.log 2>/dev/null || echo "  No logs yet. Run '$0 start' first."
    fi
    ;;

  *)
    echo "Usage: $0 {start|stop|status|restart|logs [service]}"
    echo ""
    echo "Commands:"
    echo "  start    Start all services (Docker, backend, frontend, Celery)"
    echo "  stop     Stop all services"
    echo "  status   Show service status"
    echo "  restart  Stop then start"
    echo "  logs     Tail logs: $0 logs backend"
    exit 1
    ;;
esac
