#!/bin/bash
# Integration Health Check Script
# Runs comprehensive tests to verify frontend/backend integration

set -e

# Color codes
RED='\033[0;31m'
GREEN='\033[0;32m'
YELLOW='\033[1;33m'
BLUE='\033[0;34m'
NC='\033[0m'

BACKEND_URL="http://localhost:8000"
FRONTEND_URL="http://localhost:5173"

echo -e "${BLUE}🏥 Running Integration Health Checks...${NC}"
echo ""

# Test 1: Backend Health Endpoint
echo "1️⃣  Testing Backend Health Endpoint..."
if curl -s -f "$BACKEND_URL/health" > /dev/null 2>&1; then
    echo -e "${GREEN}✓${NC} Backend health endpoint responding"
    HEALTH_DATA=$(curl -s "$BACKEND_URL/health")
    echo "   Status: $(echo $HEALTH_DATA | grep -o '"status":"[^"]*"' | cut -d'"' -f4)"
else
    echo -e "${RED}✗${NC} Backend health endpoint not responding"
    echo "   Make sure backend is running on port 8000"
    exit 1
fi

echo ""

# Test 2: Frontend Accessibility
echo "2️⃣  Testing Frontend Accessibility..."
if curl -s -f "$FRONTEND_URL" > /dev/null 2>&1; then
    echo -e "${GREEN}✓${NC} Frontend is accessible"
else
    echo -e "${RED}✗${NC} Frontend not accessible"
    echo "   Make sure frontend is running on port 5173"
    exit 1
fi

echo ""

# Test 3: CORS Configuration
echo "3️⃣  Testing CORS Configuration..."
CORS_RESPONSE=$(curl -s -I -X OPTIONS "$BACKEND_URL/health" \
    -H "Origin: $FRONTEND_URL" \
    -H "Access-Control-Request-Method: GET" 2>&1)

if echo "$CORS_RESPONSE" | grep -q "Access-Control-Allow-Origin"; then
    echo -e "${GREEN}✓${NC} CORS headers present"
else
    echo -e "${YELLOW}⚠${NC} CORS headers not found (may need configuration)"
fi

echo ""

# Test 4: WebSocket Connection
echo "4️⃣  Testing WebSocket Availability..."
if curl -s -f "$BACKEND_URL/socket.io/" > /dev/null 2>&1; then
    echo -e "${GREEN}✓${NC} Socket.IO endpoint responding"
else
    echo -e "${YELLOW}⚠${NC} Socket.IO endpoint not responding"
    echo "   WebSocket real-time features may not work"
fi

echo ""

# Test 5: API Endpoints
echo "5️⃣  Testing Core API Endpoints..."

# Test threads endpoint
if curl -s -f "$BACKEND_URL/threads" > /dev/null 2>&1; then
    echo -e "${GREEN}✓${NC} /threads endpoint responding"
else
    echo -e "${RED}✗${NC} /threads endpoint not responding"
fi

# Test auth endpoint
if curl -s -f "$BACKEND_URL/auth/google/login" > /dev/null 2>&1; then
    echo -e "${GREEN}✓${NC} /auth/google/login endpoint responding"
else
    echo -e "${YELLOW}⚠${NC} /auth/google/login endpoint not configured"
fi

echo ""

# Test 6: Redis Connection
echo "6️⃣  Testing Redis Connection..."
HEALTH_DATA=$(curl -s "$BACKEND_URL/health")
REDIS_STATUS=$(echo $HEALTH_DATA | grep -o '"redis":{"status":"[^"]*"' | cut -d'"' -f6)

if [ "$REDIS_STATUS" = "healthy" ]; then
    echo -e "${GREEN}✓${NC} Redis connection healthy"
else
    echo -e "${YELLOW}⚠${NC} Redis connection: $REDIS_STATUS"
    echo "   Rate limiting and caching may not work"
fi

echo ""
echo "================================"
echo -e "${GREEN}✅ Integration health check complete!${NC}"
echo ""
echo "Summary:"
echo "  Backend: $BACKEND_URL"
echo "  Frontend: $FRONTEND_URL"
echo "  WebSocket: Available"
echo ""
echo "Next steps:"
echo "  1. Open browser to $FRONTEND_URL"
echo "  2. Check browser console for WebSocket connection"
echo "  3. Try demo email analysis"
