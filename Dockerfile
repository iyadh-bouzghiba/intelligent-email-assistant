FROM python:3.10-slim

WORKDIR /app

# Install system dependencies
RUN apt-get update && apt-get install -y \
    build-essential \
    && rm -rf /var/lib/apt/lists/*

# Copy requirements and install
# Note: In a real project, we would have a requirements.txt
# Here we install the core ones used in the modules
RUN pip install --no-cache-dir \
    fastapi \
    uvicorn \
    pydantic \
    google-api-python-client \
    google-auth-oauthlib \
    google-auth-httplib2 \
    beautifulsoup4 \
    requests \
    torch \
    transformers

# Copy source code
COPY ./src ./src
COPY .env.example ./.env

EXPOSE 8000

# Run the assistant
CMD ["python", "src/api_app.py"]
