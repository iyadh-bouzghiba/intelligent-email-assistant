#!/bin/bash
# Stop All Services Script
# Gracefully stops all running services

set -e

# Color codes
RED='\033[0;31m'
GREEN='\033[0;32m'
YELLOW='\033[1;33m'
NC='\033[0m'

SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
PROJECT_ROOT="$(dirname "$SCRIPT_DIR")"

echo -e "${YELLOW}🛑 Stopping all services...${NC}"
echo ""

# Stop Backend
if [ -f "$PROJECT_ROOT/backend/.backend.pid" ]; then
    BACKEND_PID=$(cat "$PROJECT_ROOT/backend/.backend.pid")
    if kill -0 $BACKEND_PID 2>/dev/null; then
        echo "Stopping backend (PID: $BACKEND_PID)..."
        kill $BACKEND_PID
        rm "$PROJECT_ROOT/backend/.backend.pid"
        echo -e "${GREEN}✓${NC} Backend stopped"
    else
        echo -e "${YELLOW}⚠${NC} Backend not running"
        rm "$PROJECT_ROOT/backend/.backend.pid"
    fi
else
    echo -e "${YELLOW}⚠${NC} No backend PID file found"
fi

# Stop Frontend
if [ -f "$PROJECT_ROOT/frontend/.frontend.pid" ]; then
    FRONTEND_PID=$(cat "$PROJECT_ROOT/frontend/.frontend.pid")
    if kill -0 $FRONTEND_PID 2>/dev/null; then
        echo "Stopping frontend (PID: $FRONTEND_PID)..."
        kill $FRONTEND_PID
        rm "$PROJECT_ROOT/frontend/.frontend.pid"
        echo -e "${GREEN}✓${NC} Frontend stopped"
    else
        echo -e "${YELLOW}⚠${NC} Frontend not running"
        rm "$PROJECT_ROOT/frontend/.frontend.pid"
    fi
else
    echo -e "${YELLOW}⚠${NC} No frontend PID file found"
fi

# Optionally stop Redis (if started by start-all.sh)
if redis-cli ping &> /dev/null; then
    read -p "Stop Redis? (y/N): " -n 1 -r
    echo
    if [[ $REPLY =~ ^[Yy]$ ]]; then
        redis-cli shutdown
        echo -e "${GREEN}✓${NC} Redis stopped"
    fi
fi

echo ""
echo -e "${GREEN}✅ All services stopped${NC}"
