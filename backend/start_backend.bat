@echo off
call venv\Scripts\activate.bat
python -m uvicorn src.api.service:app --host 127.0.0.1 --port 8000 --reload
