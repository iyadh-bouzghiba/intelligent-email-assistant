# ============================================================================
# PRODUCTION-GRADE DOCKERFILE
# Intelligent Email Assistant - Render-Safe Deployment
# ============================================================================
#
# BOOT CONTRACT: python -m backend.infrastructure.worker_entry
# NO sys.path HACKS | NO WORKDIR TRICKS | FAIL-FAST VALIDATION
#
# CONTEXT: Build context is PROJECT ROOT (render.yaml: dockerContext: .)
#   COPY backend/requirements.txt  -> builder reads deps
#   COPY backend/                  -> /app/backend/  (preserves package name)
#   PYTHONPATH=/app                -> 'import backend' resolves to /app/backend/
# ============================================================================

# ===== BUILDER STAGE =====
FROM python:3.11-slim as builder

WORKDIR /build

RUN apt-get update && apt-get install -y --no-install-recommends \
    gcc g++ make libffi-dev \
    && rm -rf /var/lib/apt/lists/*

# Context is project root — requirements.txt lives in backend/
COPY backend/requirements.txt .
RUN pip install --no-cache-dir --user -r requirements.txt

# ===== RUNTIME STAGE =====
FROM python:3.11-slim

RUN useradd --create-home --shell /bin/bash appuser

WORKDIR /app

# Third-party deps from builder
COPY --from=builder /root/.local /home/appuser/.local

# Copy backend package directory — preserves 'backend' as importable package.
# Context is project root, so 'backend/' maps directly to /app/backend/.
COPY --chown=appuser:appuser backend/ ./backend/

USER appuser

ENV PATH=/home/appuser/.local/bin:$PATH
ENV PYTHONUNBUFFERED=1 \
    PYTHONDONTWRITEBYTECODE=1 \
    PYTHONPATH=/app

EXPOSE 8000

# ===== BUILD-TIME VERIFICATION (fail-fast) =====
RUN python -c "import backend; print('backend: ' + str(backend.__file__)); import backend.api; print('backend.api: OK'); import backend.infrastructure; print('backend.infrastructure: OK')" || \
    (echo "ERROR: /app/backend/ package structure broken" && exit 1)

# Health check (pure Python)
HEALTHCHECK --interval=30s --timeout=5s --start-period=15s --retries=3 \
    CMD python -c "import http.client, os; \
                   conn = http.client.HTTPConnection('localhost', int(os.getenv('PORT','8000'))); \
                   conn.request('GET', '/healthz'); \
                   exit(0 if conn.getresponse().status == 200 else 1)" || exit 1

# ===== BOOT CONTRACT ENTRYPOINT =====
# -m adds WORKDIR (/app) to sys.path.
# PYTHONPATH=/app is set for belt-and-suspenders.
# worker_entry.py runs validate_startup() then starts worker + API (hybrid).
CMD ["python", "-m", "backend.infrastructure.worker_entry"]
