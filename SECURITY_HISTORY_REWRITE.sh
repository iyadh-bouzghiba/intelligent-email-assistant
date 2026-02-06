#!/bin/bash
# SECURITY HISTORY REWRITE
# Removes exposed Fernet key from all git history
# WARNING: This rewrites history and requires force push

set -e

echo "🔒 [SECURITY] Git History Rewrite for Fernet Key Leak"
echo "=========================================="
echo ""
echo "⚠️  WARNING: This will rewrite git history"
echo "    - All collaborators must re-clone after this"
echo "    - Old clones can reintroduce the secret"
echo "    - This operation cannot be undone"
echo ""
read -p "Continue? (yes/no): " confirm

if [ "$confirm" != "yes" ]; then
    echo "Aborted."
    exit 1
fi

# The exposed secret pattern (partial, for safety)
SECRET_PATTERN="4gH-7lax4rNPoz"

echo ""
echo "Step 1: Backup current branch"
git branch backup-before-history-rewrite-$(date +%Y%m%d-%H%M%S)

echo ""
echo "Step 2: Rewrite history using filter-branch"
git filter-branch --force --index-filter \
  "git ls-files -z | xargs -0 sed -i 's/${SECRET_PATTERN}[a-zA-Z0-9_-]*/REDACTED_FERNET_KEY/g' 2>/dev/null || true" \
  --prune-empty --tag-name-filter cat -- --all

echo ""
echo "Step 3: Clean up refs"
git for-each-ref --format="delete %(refname)" refs/original | git update-ref --stdin
git reflog expire --expire=now --all
git gc --prune=now --aggressive

echo ""
echo "✅ History rewritten successfully"
echo ""
echo "Next steps:"
echo "1. Verify the secret is gone:"
echo "   git log --all -S '$SECRET_PATTERN' -- DEPLOYMENT.md"
echo ""
echo "2. Force push to remote:"
echo "   git push origin --force --all"
echo "   git push origin --force --tags"
echo ""
echo "3. Notify all collaborators to:"
echo "   - Delete their local clones"
echo "   - Re-clone from GitHub"
echo "   - NEVER push from old clones"
echo ""
echo "4. Rotate the Fernet key in Render dashboard"
echo "5. Force re-authentication for all users"
