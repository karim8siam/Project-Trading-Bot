import sys
from pathlib import Path

BASE_DIR = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(BASE_DIR / "server"))

from fastapi import Request
from main import app

@app.middleware("http")
async def vercel_path_resolver(request: Request, call_next):
    # If Vercel rewrote path to /api/index.py or stripped path, restore from headers
    matched_path = request.headers.get("x-matched-path")
    if matched_path:
        request.scope["path"] = matched_path
    return await call_next(request)
