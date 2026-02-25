@echo off
REM ========================================
REM Local AI Worker Launcher (Windows)
REM Intelligent Email Assistant
REM ========================================
REM
REM This script launches the AI worker with correct Python path
REM Run from PROJECT ROOT, not from backend directory

echo ========================================
echo Starting AI Worker (Local Development)
echo ========================================
echo.

REM Check if we're in the project root
if not exist "backend\infrastructure\ai_summarizer_worker.py" (
    echo ERROR: Must run from project root directory
    echo Current directory: %cd%
    echo Expected structure: repo-fresh\backend\infrastructure\
    pause
    exit /b 1
)

REM Check for MISTRAL_API_KEY
if "%MISTRAL_API_KEY%"=="" (
    echo WARNING: MISTRAL_API_KEY not set
    echo The worker will start but won't process jobs without API key
    echo.
    echo Set it with: set MISTRAL_API_KEY=your_key_here
    echo.
    pause
)

echo [OK] Running from project root: %cd%
echo [OK] MISTRAL_API_KEY: %MISTRAL_API_KEY:~0,20%...
echo.

REM Run worker from project root (with backend. prefix)
echo [STARTING] AI Worker...
python -m backend.infrastructure.ai_summarizer_worker

REM If worker exits, show exit code
echo.
echo ========================================
echo AI Worker stopped (Exit code: %errorlevel%)
echo ========================================
pause
