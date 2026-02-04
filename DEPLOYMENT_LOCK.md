# DEPLOYMENT LOCK — READ BEFORE TOUCHING RENDER

## Root Cause (confirmed)

Render is running this command from the **dashboard Start Command field**:

```
PYTHONPATH=. gunicorn -k uvicorn.workers.UvicornWorker src.api_app:app
```

This is **not in any file in the repository.** It is a manual override entered directly
in the Render dashboard. It takes priority over Dockerfile CMD, render.yaml, and Procfile.
No code change can override it.

The render.yaml `name: email-assistant-backend` also did not match the live service name
(`intelligent-email-assistant`), which meant render.yaml was completely disconnected from
the running service. That mismatch is now fixed.

---

## Required Dashboard Action (do this before redeploying)

### Option A — Fix the existing service (preferred)

1. Go to https://dashboard.render.com
2. Open the `intelligent-email-assistant` web service
3. Click **Settings** (left sidebar)
4. Find the **Start Command** field
5. **Delete everything in that field.** Leave it completely empty.
6. Scroll up to **Runtime** — confirm it is set to **Docker**
7. Click **Save Changes**
8. Click **Deploy > Manual Deploy** (or let the next push trigger a build)

That is it. The Dockerfile CMD will take over and the app will boot correctly.

### Option B — Delete and recreate (if Option A does not work)

1. Go to https://dashboard.render.com
2. Open `intelligent-email-assistant`
3. Settings → scroll to bottom → **Delete this Web Service**
4. Click **New** → **Web Service**
5. Connect to your GitHub repo (`intelligent-email-assistant`)
6. Set **Runtime** to **Docker**
7. Set **Dockerfile path** to `./backend/Dockerfile`
8. Set **Docker context** to `./backend`
9. Re-enter all environment variables (copy from the list below)
10. Click **Create Web Service**

---

## What the code changes fix

| File | Change | Why |
|------|--------|-----|
| backend/Dockerfile | `COPY . .` → `COPY . ./backend/` | Docker context is `./backend/`. The old COPY put files flat in `/app/` with no `backend/` subdirectory, so `import backend` failed. The new COPY creates `/app/backend/`, matching the import paths. |
| backend/Dockerfile | Removed `pip install -e .` | Not needed. `PYTHONPATH=/app` + the correct directory layout means Python finds `backend` without a pip install. Eliminates the setup.py-in-wrong-context silent failure. |
| backend/setup.py | Added `package_dir={"backend": "."}` | Fixes package discovery when run from inside `backend/` (local dev). Previously `find_packages` discovered `api`, `auth` etc. instead of `backend.api`, `backend.auth`. |
| render.yaml | `name: email-assistant-backend` → `name: intelligent-email-assistant` | The old name did not match the actual Render service. render.yaml was completely disconnected. |
| pyproject.toml | `packages = ["backend"]` → `packages.find` with `include = ["backend*"]` | Auto-discovers all sub-packages (`backend.api`, `backend.auth`, …) for root-level pip installs. |
| backend/Procfile | Deleted | Was in the wrong directory. Render looks for Procfile at project root. |
| Procfile (root) | Created: `web: python -m backend.infrastructure.worker_entry` | Correct fallback location if Docker runtime is not active. |

---

## Success criteria — deployment is fixed when logs show ONLY this

```
Building Docker image from backend/Dockerfile...
...
COPY . ./backend/
...
backend: /app/backend/__init__.py
backend.api: OK
backend.infrastructure: OK
...
Successfully built ...

[BOOT] [VALIDATION] Starting FAIL-FAST startup checks...
[OK] [VALIDATION] No 'src' contamination in sys.path
[OK] [VALIDATION] Package execution confirmed: backend.infrastructure
[OK] [VALIDATION] backend package found at: /app/backend/__init__.py
...
[BOOT] Running in API Mode
[NET] API server listening on 0.0.0.0:10000

Your service is live
```

## Deployment is STILL broken if logs contain ANY of these

- `gunicorn`
- `src.api_app`
- `src.api.service`
- `PYTHONPATH=.`
- `ModuleNotFoundError`

If any of those strings appear after a fresh deploy with an empty Start Command,
the dashboard override has not been cleared. Repeat Option A or use Option B.

---

## Environment variables (needed if recreating the service)

Set all of these in the Render dashboard for the backend service:

| Variable | Value |
|----------|-------|
| ENVIRONMENT | production |
| WORKER_MODE | false |
| LOG_LEVEL | INFO |
| LLM_MODE | api |
| JWT_ALGORITHM | HS256 |
| JWT_EXPIRE_MINUTES | 60 |
| BASE_URL | https://intelligent-email-assistant-7za8.onrender.com |
| FRONTEND_URL | https://intelligent-email-frontend.onrender.com |
| GOOGLE_REDIRECT_URI | https://intelligent-email-assistant-7za8.onrender.com/auth/callback/google |
| GOOGLE_CLIENT_ID | (from Google Cloud Console) |
| GOOGLE_CLIENT_SECRET | (from Google Cloud Console) |
| GCP_PROJECT_ID | (from Google Cloud Console) |
| GMAIL_PUBSUB_TOPIC | (from Google Cloud Console) |
| JWT_SECRET_KEY | (your secure key) |
| FERNET_KEY | (your encryption key) |
| MISTRAL_API_KEY | (from Mistral AI) |
| SUPABASE_URL | (from Supabase) |
| SUPABASE_ANON_KEY | (from Supabase) |
| SUPABASE_SERVICE_KEY | (from Supabase) |
| DATABASE_URL | (your PostgreSQL connection string) |

---

## Docker package resolution (how it works now)

```
render.yaml:  dockerContext: ./backend
                             ↓
Docker sees:  backend/__init__.py, backend/api/, backend/auth/, ...
                             ↓
Dockerfile:   COPY . ./backend/
                             ↓
/app/backend/__init__.py     ← 'import backend' finds this
/app/backend/api/service.py  ← 'from backend.api.service import sio_app' finds this
/app/backend/infrastructure/worker_entry.py
                             ↓
ENV:          PYTHONPATH=/app
                             ↓
CMD:          python -m backend.infrastructure.worker_entry
                             ↓
              validate_startup() → serve traffic
```
