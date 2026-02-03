#!/bin/bash
# OAuth Port Fix Script
# Changes PORT from 8888 to 8000 for OAuth compatibility

echo "========================================="
echo "OAUTH PORT FIX - 8888 → 8000"
echo "========================================="
echo ""

# Navigate to backend directory
cd "$(dirname "$0")/../backend" || exit 1

# Backup current .env
if [ -f .env ]; then
    cp .env .env.backup.$(date +%Y%m%d_%H%M%S)
    echo "✓ Backed up .env"
fi

# Fix PORT
sed -i 's/PORT=8888/PORT=8000/g' .env
echo "✓ Changed PORT=8888 → PORT=8000"

# Fix BASE_URL
sed -i 's|BASE_URL=http://localhost:8888|BASE_URL=http://localhost:8000|g' .env
echo "✓ Changed BASE_URL to http://localhost:8000"

# Fix REDIRECT_URI path and port
sed -i 's|REDIRECT_URI=http://localhost:8888/auth/google/callback|REDIRECT_URI=http://localhost:8000/auth/callback/google|g' .env
echo "✓ Changed REDIRECT_URI to http://localhost:8000/auth/callback/google"

# Fix any other localhost:8888 references
sed -i 's|localhost:8888|localhost:8000|g' .env
echo "✓ Fixed remaining localhost:8888 references"

# Fix OAuth path pattern
sed -i 's|/auth/google/callback|/auth/callback/google|g' .env
echo "✓ Standardized OAuth callback path"

echo ""
echo "========================================="
echo "CHANGES COMPLETE"
echo "========================================="
echo ""
echo "Summary:"
echo "  - PORT: 8000 (was 8888)"
echo "  - BASE_URL: http://localhost:8000"
echo "  - REDIRECT_URI: http://localhost:8000/auth/callback/google"
echo ""
echo "Next steps:"
echo "  1. Review: cat backend/.env"
echo "  2. Update Google Console redirect URIs"
echo "  3. Restart: python -m backend.src.infrastructure.worker_entry"
echo ""
echo "Backup saved to: .env.backup.*"
echo "========================================="
