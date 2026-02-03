# ============================================================================
# PRODUCTION-GRADE DOCKERFILE
# Intelligent Email Assistant - Render-Safe Deployment
# ============================================================================
#
# BOOT CONTRACT: python -m backend.infrastructure.worker_entry
# NO sys.path HACKS | NO WORKDIR TRICKS | FAIL-FAST VALIDATION
#
# This Dockerfile enforces package-based execution and prevents import errors
# by installing the backend as a proper Python package via setup.py
# ============================================================================

# ===== BUILDER STAGE =====
# Compile dependencies in isolated environment to minimize final image size
FROM python:3.11-slim as builder

WORKDIR /build

# Install build dependencies for Python packages with C extensions
RUN apt-get update && apt-get install -y --no-install-recommends \
    gcc \
    g++ \
    make \
    libffi-dev \
    && rm -rf /var/lib/apt/lists/*

# Copy requirements first (Docker layer caching optimization)
COPY requirements.txt .

# Install dependencies to user directory
RUN pip install --no-cache-dir --user -r requirements.txt

# ===== FINAL STAGE =====
# Minimal runtime image without build tools
FROM python:3.11-slim

# Create non-root user for security
RUN useradd --create-home --shell /bin/bash appuser

# Set working directory
WORKDIR /app

# Copy compiled dependencies from builder stage
COPY --from=builder /root/.local /home/appuser/.local

# Copy entire backend package
COPY --chown=appuser:appuser . .

# Switch to appuser before installing package
USER appuser

# Install backend package in user space
# This creates the 'backend' package that can be imported
RUN pip install --user --no-cache-dir -e .

# Verify package installation (fail-fast if broken)
RUN python -c "import backend; print(f'✅ Backend package installed: {backend.__file__}')" || \
    (echo "❌ ERROR: Backend package installation failed" && exit 1)

# Set PATH to include user-installed binaries
ENV PATH=/home/appuser/.local/bin:$PATH

# Python configuration for optimal Docker performance
ENV PYTHONUNBUFFERED=1 \
    PYTHONDONTWRITEBYTECODE=1 \
    PYTHONPATH=/app

# Expose port (Render will override with $PORT env var)
EXPOSE 8000

# Health check using pure Python (no external dependencies)
HEALTHCHECK --interval=30s --timeout=5s --start-period=15s --retries=3 \
    CMD python -c "import http.client, os; \
                   port = os.getenv('PORT', '8000'); \
                   conn = http.client.HTTPConnection('localhost', int(port)); \
                   conn.request('GET', '/health'); \
                   r = conn.getresponse(); \
                   exit(0 if r.status == 200 else 1)" || exit 1

# ===== BOOT CONTRACT ENFORCEMENT =====
# CANONICAL ENTRYPOINT - DO NOT MODIFY
# This command:
# - Executes backend as a Python module (-m flag)
# - Automatically resolves 'from backend.xxx' imports
# - Triggers validate_startup() before serving requests
# - Respects $PORT environment variable from Render
# ============================================================================
CMD ["python", "-m", "backend.infrastructure.worker_entry"]
