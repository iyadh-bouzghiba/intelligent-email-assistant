#!/usr/bin/env pwsh
# ENV-BOOT-01: Smoke test for pure imports
# Verifies that importing backend modules does NOT require environment variables
# This script MUST pass even when JWT_SECRET_KEY is unset

$ErrorActionPreference = "Continue"

# UTF-8 encoding guard for cross-platform compatibility
[Console]::OutputEncoding = [System.Text.UTF8Encoding]::new()
$env:PYTHONUTF8 = '1'

Write-Host "[SMOKE] ENV-BOOT-01: Testing import purity..." -ForegroundColor Cyan

# Unset JWT_SECRET_KEY to ensure imports don't require it
$env:JWT_SECRET_KEY = $null

# Get repo root (script is in repo-fresh/scripts/)
$RepoRoot = Split-Path -Parent $PSScriptRoot
Set-Location $RepoRoot

Write-Host "[SMOKE] Working directory: $RepoRoot" -ForegroundColor Gray

# Helper function to run Python import and check success
function Test-Import {
    param($ImportStatement, $TestName)

    Write-Host "[TEST] $TestName..." -ForegroundColor Yellow

    # Capture output and check exit code
    $output = python -c $ImportStatement 2>&1 | Out-String
    $exitCode = $LASTEXITCODE

    # Filter success message from output
    $successLine = $output -split "`n" | Where-Object { $_ -match '\[OK\]' }

    if ($exitCode -ne 0) {
        Write-Host "[FAIL] $TestName failed (exit code: $exitCode)" -ForegroundColor Red
        Write-Host $output -ForegroundColor Red
        return $false
    }

    if ($successLine) {
        Write-Host $successLine -ForegroundColor Green
    } else {
        Write-Host "[OK] $TestName completed" -ForegroundColor Green
    }

    return $true
}

# Test 1: Import backend package
$test1 = Test-Import "import backend; print('[OK] backend imported')" "backend"
if (-not $test1) { exit 1 }

# Test 2: Import backend.api.service (must not require JWT_SECRET_KEY)
$test2 = Test-Import "import backend.api.service; print('[OK] backend.api.service imported')" "backend.api.service"
if (-not $test2) { exit 1 }

# Test 3: Import backend.infrastructure.worker_entry
$test3 = Test-Import "import backend.infrastructure.worker_entry; print('[OK] worker_entry imported')" "backend.infrastructure.worker_entry"
if (-not $test3) { exit 1 }

Write-Host ""
Write-Host "[PASS] All imports succeeded without JWT_SECRET_KEY" -ForegroundColor Green
Write-Host "[PASS] ENV-BOOT-01 validation complete" -ForegroundColor Green
exit 0
