import sys
import traceback
from pathlib import Path
from fastapi import FastAPI
from fastapi.responses import JSONResponse

BASE_DIR = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(BASE_DIR))
sys.path.insert(0, str(BASE_DIR / "server"))

try:
    from main import app
except Exception as e:
    tb = traceback.format_exc()
    app = FastAPI()
    
    @app.api_route("/{path_name:path}", methods=["GET", "POST", "PUT", "DELETE"])
    def catch_all(path_name: str):
        return JSONResponse(status_code=500, content={"error": str(e), "traceback": tb.split("\n")})
