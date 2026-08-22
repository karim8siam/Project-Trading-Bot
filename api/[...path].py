import sys
from pathlib import Path

BASE_DIR = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(BASE_DIR / "server"))

from fastapi import FastAPI, Request
from fastapi.middleware.cors import CORSMiddleware
from main import api_router

# Create dedicated Vercel ASGI Application
app = FastAPI(title="Orbital Trading Vercel API")

app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

@app.middleware("http")
async def restore_vercel_path(request: Request, call_next):
    # Restore original client path from Vercel headers if rewritten
    orig_path = request.headers.get("x-matched-path") or request.headers.get("x-forwarded-uri")
    if orig_path:
        request.scope["path"] = orig_path
    return await call_next(request)

# Mount all API routes under /api, /api/index.py, and root
app.include_router(api_router, prefix="/api")
app.include_router(api_router, prefix="")
app.include_router(api_router, prefix="/api/index.py")
