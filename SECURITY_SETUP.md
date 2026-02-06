# Security Setup Guide

## Prevent Secret Leaks

### Option 1: GitGuardian (Recommended)

GitGuardian is already monitoring this repository. To configure:

1. **Enable GitGuardian GitHub App**
   - Visit: https://github.com/apps/gitguardian
   - Install for repository: `iyadh-bouzghiba/intelligent-email-assistant`
   - Grants: Read access to code, commit statuses

2. **Configure Alerts**
   - Dashboard: https://dashboard.gitguardian.com
   - Set notification preferences
   - Review detected incidents immediately

3. **Remediation Workflow**
   - GitGuardian detects secret in commit
   - Creates GitHub issue automatically
   - Follow remediation: rotate key, rewrite history, update docs

### Option 2: Pre-commit Hook (Local)

Install a local secret scanner:

```bash
# Install pre-commit framework
pip install pre-commit

# Create .pre-commit-config.yaml
cat > .pre-commit-config.yaml <<'EOF'
repos:
  - repo: https://github.com/Yelp/detect-secrets
    rev: v1.4.0
    hooks:
      - id: detect-secrets
        args: ['--baseline', '.secrets.baseline']
        exclude: package-lock.json
EOF

# Initialize baseline
detect-secrets scan > .secrets.baseline

# Install hooks
pre-commit install
```

Now every commit will be scanned for secrets before push.

### Option 3: GitHub Actions CI Check

Add to `.github/workflows/security.yml`:

```yaml
name: Security Scan

on: [push, pull_request]

jobs:
  scan-secrets:
    runs-on: ubuntu-latest
    steps:
      - uses: actions/checkout@v3
        with:
          fetch-depth: 0

      - name: TruffleHog Secret Scan
        uses: trufflesecurity/trufflehog@main
        with:
          path: ./
          base: main
          head: HEAD
```

## Secret Management Best Practices

### ✅ DO:
- Store secrets ONLY in:
  - Render dashboard environment variables
  - Local `.env` files (gitignored)
  - Password manager / secrets vault
- Use placeholder values in documentation
- Generate secrets locally, never in chat/email
- Rotate immediately if exposed
- Use environment-specific keys (dev/staging/prod)

### ❌ DON'T:
- Commit `.env` files
- Hardcode secrets in code/configs
- Share secrets in chat, email, screenshots
- Reuse secrets across environments
- Store secrets in documentation
- Log secret values

## Key Rotation Procedure

When a secret is exposed:

1. **Immediate**: Generate new secret
2. **Update**: Set in Render dashboard
3. **Remove**: Delete from code/history
4. **Rewrite**: Purge from git history
5. **Notify**: Alert all collaborators
6. **Verify**: Confirm app works with new secret

## Environment Variable Setup

All secrets must be set in Render dashboard:

**Backend Service → Environment:**

```bash
# Generate Fernet key
python -c "from cryptography.fernet import Fernet; print(Fernet.generate_key().decode())"

# Set in Render (NEVER commit)
FERNET_KEY=<generated_key>
SUPABASE_SERVICE_KEY=<from_supabase_dashboard>
GOOGLE_CLIENT_SECRET=<from_google_cloud_console>
MISTRAL_API_KEY=<from_mistral_ai>
JWT_SECRET_KEY=<generate_random_secure_string>
```

**Frontend Service → Environment:**

```bash
VITE_API_BASE=https://intelligent-email-assistant-3e1a.onrender.com
VITE_SOCKET_URL=https://intelligent-email-assistant-3e1a.onrender.com
```

## Incident Response Checklist

If GitGuardian alerts you:

- [ ] Acknowledge alert immediately
- [ ] Identify leaked secret type
- [ ] Generate replacement secret
- [ ] Update Render environment variables
- [ ] Remove secret from current HEAD (commit)
- [ ] Push secret removal
- [ ] Run history rewrite script
- [ ] Force push cleaned history
- [ ] Notify collaborators to re-clone
- [ ] Verify application still works
- [ ] Mark GitGuardian incident as resolved

## Contact

For security issues: Create private GitHub Security Advisory

GitGuardian Support: https://support.gitguardian.com
