#!/bin/bash
# Production Deployment Script
# Intelligent Email Assistant - Zero-Budget AI Summarization

set -e  # Exit on error

echo "========================================"
echo "PRODUCTION DEPLOYMENT"
echo "Intelligent Email Assistant"
echo "Phase 1: Zero-Budget AI Summarization"
echo "========================================"
echo ""

# Check environment variables
echo "🔍 Checking environment variables..."
if [ -z "$MISTRAL_API_KEY" ]; then
    echo "❌ ERROR: MISTRAL_API_KEY not set"
    echo "   Set it: export MISTRAL_API_KEY='your_key_here'"
    exit 1
fi
echo "✅ MISTRAL_API_KEY: SET"

# Install dependencies
echo ""
echo "📦 Installing dependencies..."
cd backend
pip install -q beautifulsoup4 PyJWT
echo "✅ Dependencies installed"

# Stop existing services
echo ""
echo "🛑 Stopping existing services..."
pkill -f "ai_summarizer_worker" || true
pkill -f "uvicorn backend.api.service" || true
sleep 2
echo "✅ Services stopped"

# Create logs directory
mkdir -p logs
echo "✅ Logs directory ready"

# Start AI Worker
echo ""
echo "🚀 Starting AI Worker..."
nohup python -m infrastructure.ai_summarizer_worker > logs/ai_worker.log 2>&1 &
WORKER_PID=$!
sleep 2

if ps -p $WORKER_PID > /dev/null; then
    echo "✅ AI Worker started (PID: $WORKER_PID)"
else
    echo "❌ AI Worker failed to start"
    tail -20 logs/ai_worker.log
    exit 1
fi

# Start Backend API
echo ""
echo "🚀 Starting Backend API..."
nohup uvicorn api.service:sio_app --host 0.0.0.0 --port 8000 > logs/api.log 2>&1 &
API_PID=$!
sleep 3

if ps -p $API_PID > /dev/null; then
    echo "✅ Backend API started (PID: $API_PID)"
else
    echo "❌ Backend API failed to start"
    tail -20 logs/api.log
    exit 1
fi

# Health check
echo ""
echo "🏥 Running health check..."
sleep 2
HEALTH_RESPONSE=$(curl -s http://localhost:8000/health || echo '{"status":"error"}')
if echo "$HEALTH_RESPONSE" | grep -q "healthy"; then
    echo "✅ Health check passed"
else
    echo "⚠️  Health check warning: $HEALTH_RESPONSE"
fi

# Display logs
echo ""
echo "========================================"
echo "✅ DEPLOYMENT COMPLETE"
echo "========================================"
echo ""
echo "Services:"
echo "  Backend API: http://localhost:8000"
echo "  AI Worker: PID $WORKER_PID"
echo ""
echo "Logs:"
echo "  API: tail -f backend/logs/api.log"
echo "  Worker: tail -f backend/logs/ai_worker.log"
echo ""
echo "Monitoring:"
echo "  tail -f backend/logs/ai_worker.log | grep -E 'Processing|Preprocessing|Mistral'"
echo ""
echo "Stop services:"
echo "  pkill -f ai_summarizer_worker"
echo "  pkill -f uvicorn"
echo ""
echo "Next steps:"
echo "  1. Start frontend: cd frontend && npm run dev"
echo "  2. Monitor logs for 30 minutes"
echo "  3. Sync emails and verify AI summaries appear"
echo ""
