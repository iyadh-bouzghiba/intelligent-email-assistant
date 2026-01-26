#!/bin/bash

# Activate virtual environment
source venv/Scripts/activate

# Run the server
python -m uvicorn src.api.service:app --host 127.0.0.1 --port 8000 --reload
