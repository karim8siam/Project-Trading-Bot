import sys
from pathlib import Path

BASE_DIR = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(BASE_DIR / "server"))

from fastapi import Request
from fastapi.responses import JSONResponse
from main import app, api_router

# Ensure all routes are directly on app as well
app.include_router(api_router, prefix="")
app.include_router(api_router, prefix="/api")
app.include_router(api_router, prefix="/api/index.py")

@app.get("/debug-path")
@app.get("/api/debug-path")
def debug_path(request: Request):
    return {
        "url_path": str(request.url.path),
        "scope_path": request.scope.get("path"),
        "raw_path": str(request.scope.get("raw_path")),
        "headers": dict(request.headers)
    }
