#!/bin/bash
# ========================================
# Local AI Worker Launcher (Linux/Mac)
# Intelligent Email Assistant
# ========================================
#
# This script launches the AI worker with correct Python path
# Run from PROJECT ROOT, not from backend directory

echo "========================================"
echo "Starting AI Worker (Local Development)"
echo "========================================"
echo ""

# Check if we're in the project root
if [ ! -f "backend/infrastructure/ai_summarizer_worker.py" ]; then
    echo "ERROR: Must run from project root directory"
    echo "Current directory: $(pwd)"
    echo "Expected structure: repo-fresh/backend/infrastructure/"
    exit 1
fi

# Check for MISTRAL_API_KEY
if [ -z "$MISTRAL_API_KEY" ]; then
    echo "WARNING: MISTRAL_API_KEY not set"
    echo "The worker will start but won't process jobs without API key"
    echo ""
    echo "Set it with: export MISTRAL_API_KEY='your_key_here'"
    echo ""
    read -p "Press Enter to continue anyway..."
fi

echo "[OK] Running from project root: $(pwd)"
echo "[OK] MISTRAL_API_KEY: ${MISTRAL_API_KEY:0:20}..."
echo ""

# Run worker from project root (with backend. prefix)
echo "[STARTING] AI Worker..."
python -m backend.infrastructure.ai_summarizer_worker

# If worker exits, show exit code
EXIT_CODE=$?
echo ""
echo "========================================"
echo "AI Worker stopped (Exit code: $EXIT_CODE)"
echo "========================================"
