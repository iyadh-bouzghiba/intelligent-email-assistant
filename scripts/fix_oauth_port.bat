@echo off
REM OAuth Port Fix Script for Windows
REM Changes PORT from 8888 to 8000 for OAuth compatibility

echo =========================================
echo OAUTH PORT FIX - 8888 to 8000
echo =========================================
echo.

cd /d "%~dp0..\backend"

REM Backup current .env
if exist .env (
    copy .env .env.backup.%date:~-4,4%%date:~-10,2%%date:~-7,2%_%time:~0,2%%time:~3,2%%time:~6,2%
    echo [OK] Backed up .env
)

REM Fix PORT
powershell -Command "(Get-Content .env) -replace 'PORT=8888', 'PORT=8000' | Set-Content .env"
echo [OK] Changed PORT=8888 to PORT=8000

REM Fix BASE_URL
powershell -Command "(Get-Content .env) -replace 'BASE_URL=http://localhost:8888', 'BASE_URL=http://localhost:8000' | Set-Content .env"
echo [OK] Changed BASE_URL to http://localhost:8000

REM Fix REDIRECT_URI path and port
powershell -Command "(Get-Content .env) -replace 'REDIRECT_URI=http://localhost:8888/auth/google/callback', 'REDIRECT_URI=http://localhost:8000/auth/callback/google' | Set-Content .env"
echo [OK] Changed REDIRECT_URI to http://localhost:8000/auth/callback/google

REM Fix any other localhost:8888 references
powershell -Command "(Get-Content .env) -replace 'localhost:8888', 'localhost:8000' | Set-Content .env"
echo [OK] Fixed remaining localhost:8888 references

REM Fix OAuth path pattern
powershell -Command "(Get-Content .env) -replace '/auth/google/callback', '/auth/callback/google' | Set-Content .env"
echo [OK] Standardized OAuth callback path

echo.
echo =========================================
echo CHANGES COMPLETE
echo =========================================
echo.
echo Summary:
echo   - PORT: 8000 (was 8888)
echo   - BASE_URL: http://localhost:8000
echo   - REDIRECT_URI: http://localhost:8000/auth/callback/google
echo.
echo Next steps:
echo   1. Review: type backend\.env
echo   2. Update Google Console redirect URIs
echo   3. Restart: python -m backend.src.infrastructure.worker_entry
echo.
echo Backup saved to: .env.backup.*
echo =========================================
pause
