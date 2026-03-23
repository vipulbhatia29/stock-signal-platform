#!/bin/bash
# stock-signal-platform setup script
# Works on macOS, Linux (Ubuntu/Debian), and WSL2 (Windows)
#
# Usage:
#   chmod +x setup.sh
#   ./setup.sh          # Full setup
#   ./setup.sh --check  # Check prerequisites only

set -e

RED='\033[0;31m'
GREEN='\033[0;32m'
YELLOW='\033[1;33m'
CYAN='\033[0;36m'
NC='\033[0m'

OS="$(uname -s)"
ARCH="$(uname -m)"

ok()   { echo -e "  ${GREEN}✓${NC} $1"; }
warn() { echo -e "  ${YELLOW}!${NC} $1"; }
fail() { echo -e "  ${RED}✗${NC} $1"; }

# ─── Detect Platform ─────────────────────────────────────────────────────────

detect_platform() {
  case "$OS" in
    Darwin)  PLATFORM="macos" ;;
    Linux)
      if grep -qi microsoft /proc/version 2>/dev/null; then
        PLATFORM="wsl"
      else
        PLATFORM="linux"
      fi
      ;;
    MINGW*|MSYS*|CYGWIN*)
      echo -e "${RED}Native Windows is not supported. Use WSL2:${NC}"
      echo "  1. wsl --install"
      echo "  2. Open Ubuntu terminal"
      echo "  3. Re-run this script inside WSL2"
      exit 1
      ;;
    *)
      echo -e "${RED}Unsupported OS: $OS${NC}"
      exit 1
      ;;
  esac
  echo -e "${CYAN}Platform: $PLATFORM ($OS $ARCH)${NC}"
}

# ─── Check Prerequisites ─────────────────────────────────────────────────────

check_prerequisites() {
  echo ""
  echo -e "${CYAN}Checking prerequisites...${NC}"
  local missing=0

  # Python 3.12+
  if command -v python3 &>/dev/null; then
    PY_VER=$(python3 -c "import sys; print(f'{sys.version_info.major}.{sys.version_info.minor}')")
    PY_MAJOR=$(echo "$PY_VER" | cut -d. -f1)
    PY_MINOR=$(echo "$PY_VER" | cut -d. -f2)
    if [ "$PY_MAJOR" -ge 3 ] && [ "$PY_MINOR" -ge 12 ]; then
      ok "Python $PY_VER"
    else
      fail "Python $PY_VER (need 3.12+)"
      missing=1
    fi
  else
    fail "Python not found"
    missing=1
  fi

  # uv
  if command -v uv &>/dev/null; then
    ok "uv $(uv --version 2>/dev/null | head -1)"
  else
    fail "uv not found"
    warn "Install: curl -LsSf https://astral.sh/uv/install.sh | sh"
    missing=1
  fi

  # Node.js 20+
  if command -v node &>/dev/null; then
    NODE_VER=$(node --version | sed 's/v//')
    NODE_MAJOR=$(echo "$NODE_VER" | cut -d. -f1)
    if [ "$NODE_MAJOR" -ge 20 ]; then
      ok "Node.js $NODE_VER"
    else
      fail "Node.js $NODE_VER (need 20+)"
      missing=1
    fi
  else
    fail "Node.js not found"
    missing=1
  fi

  # npm
  if command -v npm &>/dev/null; then
    ok "npm $(npm --version)"
  else
    fail "npm not found"
    missing=1
  fi

  # Docker
  if command -v docker &>/dev/null; then
    if docker info &>/dev/null; then
      ok "Docker $(docker --version | grep -oE '[0-9]+\.[0-9]+\.[0-9]+')"
    else
      fail "Docker installed but daemon not running"
      case "$PLATFORM" in
        macos) warn "Start Docker Desktop" ;;
        linux|wsl) warn "Run: sudo systemctl start docker" ;;
      esac
      missing=1
    fi
  else
    fail "Docker not found"
    case "$PLATFORM" in
      macos) warn "Install: brew install --cask docker" ;;
      linux)  warn "Install: https://docs.docker.com/engine/install/" ;;
      wsl)    warn "Install Docker Desktop for Windows, enable WSL2 integration" ;;
    esac
    missing=1
  fi

  # docker compose
  if docker compose version &>/dev/null; then
    ok "docker compose $(docker compose version --short 2>/dev/null)"
  else
    fail "docker compose not found"
    missing=1
  fi

  # Git
  if command -v git &>/dev/null; then
    ok "git $(git --version | grep -oE '[0-9]+\.[0-9]+\.[0-9]+')"
  else
    fail "git not found"
    missing=1
  fi

  echo ""
  if [ "$missing" -eq 0 ]; then
    ok "All prerequisites met"
  else
    fail "Missing prerequisites — install them and re-run"
    exit 1
  fi
}

# ─── Install Platform-Specific Dependencies ──────────────────────────────────

install_platform_deps() {
  echo ""
  echo -e "${CYAN}Installing platform-specific dependencies...${NC}"

  case "$PLATFORM" in
    macos)
      # Prophet needs cmdstan; brew handles native deps
      if ! command -v brew &>/dev/null; then
        warn "Homebrew not found. Some packages may need manual install."
      fi
      ;;
    linux|wsl)
      # Prophet build dependencies
      if command -v apt-get &>/dev/null; then
        echo "  Installing build dependencies (may need sudo)..."
        sudo apt-get update -qq
        sudo apt-get install -y -qq build-essential python3-dev libpq-dev > /dev/null 2>&1
        ok "Build dependencies installed"
      elif command -v dnf &>/dev/null; then
        sudo dnf install -y gcc python3-devel postgresql-devel > /dev/null 2>&1
        ok "Build dependencies installed (dnf)"
      else
        warn "Unknown package manager — ensure gcc, python3-dev, libpq-dev are installed"
      fi
      ;;
  esac
}

# ─── Project Setup ────────────────────────────────────────────────────────────

setup_project() {
  echo ""
  echo -e "${CYAN}Setting up project...${NC}"

  # Python dependencies
  echo -e "${GREEN}[1/5] Installing Python dependencies...${NC}"
  uv sync
  ok "Python dependencies installed"

  # Frontend dependencies
  echo -e "${GREEN}[2/5] Installing frontend dependencies...${NC}"
  cd frontend && npm install && cd ..
  ok "Frontend dependencies installed"

  # Environment file
  echo -e "${GREEN}[3/5] Setting up environment...${NC}"
  if [ ! -f backend/.env ]; then
    if [ -f backend/.env.example ]; then
      cp backend/.env.example backend/.env
      warn "Created backend/.env from .env.example — edit with your secrets"
    else
      cat > backend/.env << 'ENVEOF'
# Database
DATABASE_URL=postgresql+asyncpg://stocksignal:stocksignal@localhost:5433/stocksignal

# Redis
REDIS_URL=redis://localhost:6380/0

# JWT (generate your own: python -c "import secrets; print(secrets.token_urlsafe(32))")
JWT_SECRET_KEY=change-me-to-a-random-secret
JWT_ALGORITHM=HS256

# LLM providers (at least one required for chat agent)
GROQ_API_KEY=
ANTHROPIC_API_KEY=

# Feature flags
AGENT_V2=true
ENVEOF
      warn "Created backend/.env with defaults — edit JWT_SECRET_KEY and API keys"
    fi
  else
    ok "backend/.env already exists"
  fi

  # Docker infrastructure
  echo -e "${GREEN}[4/5] Starting Docker services...${NC}"
  docker compose up -d postgres redis
  echo "  Waiting for Postgres health check..."
  until docker compose exec -T postgres pg_isready -U stocksignal > /dev/null 2>&1; do
    sleep 1
  done
  ok "Postgres (port 5433) + Redis (port 6380) running"

  # Database migrations
  echo -e "${GREEN}[5/5] Running database migrations...${NC}"
  uv run alembic upgrade head
  ok "Database schema up to date"

  # Summary
  echo ""
  echo -e "${GREEN}════════════════════════════════════════════════${NC}"
  echo -e "${GREEN}  Setup complete!${NC}"
  echo -e "${GREEN}════════════════════════════════════════════════${NC}"
  echo ""
  echo "Next steps:"
  echo ""
  echo "  1. Edit backend/.env with your JWT secret and API keys"
  echo ""
  echo "  2. Bootstrap data (optional, ~25 min):"
  echo "     uv run python -m scripts.sync_sp500"
  echo "     uv run python -m scripts.seed_etfs"
  echo "     uv run python -m scripts.seed_prices --universe"
  echo "     uv run python -m scripts.sync_indexes"
  echo "     uv run python -m scripts.seed_fundamentals --universe"
  echo "     uv run python -m scripts.seed_dividends --universe"
  echo "     uv run python -m scripts.seed_forecasts --universe"
  echo ""
  echo "  3. Start all services:"
  echo "     ./run.sh start"
  echo ""
  echo "  4. Open in browser:"
  echo "     http://localhost:3000"
  echo ""
}

# ─── Main ─────────────────────────────────────────────────────────────────────

detect_platform

if [ "$1" = "--check" ]; then
  check_prerequisites
  exit 0
fi

check_prerequisites
install_platform_deps
setup_project
