import uvicorn
from src.api.service import app

if __name__ == "__main__":
    # Start the production server
    # In a real K8s/Docker env, this would be run via gunicorn/uvicorn CLI
    uvicorn.run(app, host="0.0.0.0", port=8000)
