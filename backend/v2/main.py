"""
FastAPI v2 — authenticated routes requiring Cognito JWT.
Phase 1 (backend/app/main.py) is FROZEN and runs independently.
"""

import logging
import os

from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware
from mangum import Mangum
from pythonjsonlogger import jsonlogger

from .routers import analyze, results, scans

# ── Structured JSON logging ────────────────────────────────────────────────────
root_logger = logging.getLogger()
_handler = logging.StreamHandler()
_handler.setFormatter(
    jsonlogger.JsonFormatter(
        fmt="%(asctime)s %(name)s %(levelname)s %(message)s",
        datefmt="%Y-%m-%dT%H:%M:%S",
    )
)
root_logger.addHandler(_handler)
root_logger.setLevel(os.getenv("LOG_LEVEL", "INFO"))

# ── FastAPI application ────────────────────────────────────────────────────────
app = FastAPI(
    title="DocImgAnalizer API v2",
    version="2.0.0",
    docs_url=None,
    redoc_url=None,
    openapi_url=None,
)

_env = os.getenv("ENVIRONMENT", "dev")
_allowed_origin = (
    "https://imgapp.craftingnewtech.com"
    if _env == "prod"
    else "https://dev-imgapp.craftingnewtech.com"
)

app.add_middleware(
    CORSMiddleware,
    allow_origins=[_allowed_origin],
    allow_methods=["GET", "POST", "DELETE", "OPTIONS"],
    allow_headers=["Content-Type", "Authorization"],
    max_age=3600,
)

app.include_router(analyze.router, prefix="/api/v2")
app.include_router(results.router, prefix="/api/v2")
app.include_router(scans.router, prefix="/api/v2")


@app.get("/api/v2/health")
def health() -> dict:
    return {"status": "ok", "version": "2", "environment": _env}


handler = Mangum(app, lifespan="off")
