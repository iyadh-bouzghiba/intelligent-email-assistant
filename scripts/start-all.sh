#!/bin/bash
# Unified Startup Script for Git Bash
# Starts Backend, Frontend, and Redis concurrently with proper logging

set -e

# Color codes
RED='\033[0;31m'
GREEN='\033[0;32m'
YELLOW='\033[1;33m'
BLUE='\033[0;34m'
CYAN='\033[0;36m'
NC='\033[0m'

# Get script directory
SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
PROJECT_ROOT="$(dirname "$SCRIPT_DIR")"

echo -e "${BLUE}╔════════════════════════════════════════╗${NC}"
echo -e "${BLUE}║   Email Assistant - Unified Startup   ║${NC}"
echo -e "${BLUE}╚════════════════════════════════════════╝${NC}"
echo ""

# Step 1: Environment Validation
echo -e "${CYAN}[1/5]${NC} Validating environment..."
if bash "$SCRIPT_DIR/check-env.sh"; then
    echo -e "${GREEN}✓${NC} Environment validation passed"
else
    echo -e "${RED}✗${NC} Environment validation failed"
    exit 1
fi

echo ""

# Step 2: Check if Redis is needed
echo -e "${CYAN}[2/5]${NC} Checking Redis..."
if command -v redis-server &> /dev/null; then
    echo -e "${GREEN}✓${NC} Redis found"
    
    # Check if Redis is already running
    if redis-cli ping &> /dev/null; then
        echo -e "${YELLOW}⚠${NC} Redis already running"
    else
        echo -e "${BLUE}→${NC} Starting Redis..."
        redis-server --daemonize yes --port 6379
        sleep 2
        if redis-cli ping &> /dev/null; then
            echo -e "${GREEN}✓${NC} Redis started successfully"
        else
            echo -e "${RED}✗${NC} Failed to start Redis"
        fi
    fi
else
    echo -e "${YELLOW}⚠${NC} Redis not found (using Docker or external Redis)"
fi

echo ""

# Step 3: Start Backend
echo -e "${CYAN}[3/5]${NC} Starting Backend..."
cd "$PROJECT_ROOT/backend"

# Check if virtual environment exists
if [ ! -d "venv" ]; then
    echo -e "${YELLOW}⚠${NC} Virtual environment not found, creating..."
    python -m venv venv
fi

# Activate virtual environment
source venv/Scripts/activate || source venv/bin/activate

# Install dependencies if needed
if [ ! -f "venv/.installed" ]; then
    echo -e "${BLUE}→${NC} Installing Python dependencies..."
    pip install -q -r requirements.txt
    touch venv/.installed
fi

# Start backend in background
echo -e "${BLUE}→${NC} Launching backend server..."
nohup python -m uvicorn src.api.service:app --host 0.0.0.0 --port 8000 --reload \
    > logs/backend.log 2>&1 &
BACKEND_PID=$!
echo $BACKEND_PID > .backend.pid
echo -e "${GREEN}✓${NC} Backend started (PID: $BACKEND_PID)"
echo "   Logs: backend/logs/backend.log"

echo ""

# Step 4: Start Frontend
echo -e "${CYAN}[4/5]${NC} Starting Frontend..."
cd "$PROJECT_ROOT/frontend"

# Install dependencies if needed
if [ ! -d "node_modules" ]; then
    echo -e "${BLUE}→${NC} Installing Node dependencies..."
    npm install
fi

# Start frontend in background
echo -e "${BLUE}→${NC} Launching frontend server..."
nohup npm run dev > logs/frontend.log 2>&1 &
FRONTEND_PID=$!
echo $FRONTEND_PID > .frontend.pid
echo -e "${GREEN}✓${NC} Frontend started (PID: $FRONTEND_PID)"
echo "   Logs: frontend/logs/frontend.log"

echo ""

# Step 5: Wait for services to be ready
echo -e "${CYAN}[5/5]${NC} Waiting for services to be ready..."
sleep 5

# Run health check
echo ""
bash "$SCRIPT_DIR/health-check.sh"

echo ""
echo -e "${GREEN}╔════════════════════════════════════════╗${NC}"
echo -e "${GREEN}║     All Services Started! 🚀           ║${NC}"
echo -e "${GREEN}╚════════════════════════════════════════╝${NC}"
echo ""
echo "Services:"
echo "  🔹 Backend:  http://localhost:8000"
echo "  🔹 Frontend: http://localhost:5173"
echo "  🔹 Health:   http://localhost:8000/health"
echo ""
echo "Process IDs:"
echo "  Backend:  $BACKEND_PID"
echo "  Frontend: $FRONTEND_PID"
echo ""
echo "To stop all services:"
echo "  bash scripts/stop-all.sh"
echo ""
echo "To view logs:"
echo "  tail -f backend/logs/backend.log"
echo "  tail -f frontend/logs/frontend.log"
echo ""
