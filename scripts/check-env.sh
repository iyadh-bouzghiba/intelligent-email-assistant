#!/bin/bash
# Environment Validation Script
# Checks that all required environment variables are set before starting services

set -e

echo "🔍 Checking environment variables..."

# Color codes
RED='\033[0;31m'
GREEN='\033[0;32m'
YELLOW='\033[1;33m'
NC='\033[0m' # No Color

MISSING_VARS=()
OPTIONAL_VARS=()

# Function to check required variable
check_required() {
    local var_name=$1
    if [ -z "${!var_name}" ]; then
        MISSING_VARS+=("$var_name")
        echo -e "${RED}✗${NC} $var_name - MISSING (REQUIRED)"
    else
        echo -e "${GREEN}✓${NC} $var_name - Set"
    fi
}

# Function to check optional variable
check_optional() {
    local var_name=$1
    if [ -z "${!var_name}" ]; then
        OPTIONAL_VARS+=("$var_name")
        echo -e "${YELLOW}⚠${NC} $var_name - Not set (optional)"
    else
        echo -e "${GREEN}✓${NC} $var_name - Set"
    fi
}

# Load .env file if it exists
if [ -f "backend/.env" ]; then
    echo "📄 Loading backend/.env file..."
    export $(cat backend/.env | grep -v '^#' | xargs)
fi

echo ""
echo "=== Critical Variables ==="
check_required "JWT_SECRET_KEY"

echo ""
echo "=== OAuth2 Variables ==="
check_optional "GOOGLE_CLIENT_ID"
check_optional "GOOGLE_CLIENT_SECRET"

echo ""
echo "=== AI & Services ==="
check_optional "MISTRAL_API_KEY"

echo ""
echo "=== Infrastructure ==="
check_optional "REDIS_HOST"
check_optional "REDIS_PORT"

echo ""
echo "=== Application Config ==="
check_optional "ENVIRONMENT"
check_optional "FRONTEND_URL"

echo ""
echo "================================"

if [ ${#MISSING_VARS[@]} -gt 0 ]; then
    echo -e "${RED}❌ CRITICAL: Missing required variables!${NC}"
    echo "Please set the following in backend/.env:"
    for var in "${MISSING_VARS[@]}"; do
        echo "  - $var"
    done
    exit 1
fi

if [ ${#OPTIONAL_VARS[@]} -gt 0 ]; then
    echo -e "${YELLOW}⚠️  WARNING: Some optional variables not set${NC}"
    echo "The following features may be limited:"
    for var in "${OPTIONAL_VARS[@]}"; do
        echo "  - $var"
    done
    echo ""
fi

echo -e "${GREEN}✅ Environment validation passed!${NC}"
exit 0
