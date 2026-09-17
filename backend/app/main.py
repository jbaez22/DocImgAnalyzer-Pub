# FROZEN — Phase 1. No modifications after 2026-06-19.
# All new backend work goes into backend/v2/
import logging
import os

from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware
from mangum import Mangum
from pythonjsonlogger import jsonlogger

from app.routers import analyze, results

# ── Structured JSON logging ────────────────────────────────────────────────────
# CloudWatch Log Insights can query these fields directly.
root_logger = logging.getLogger()
_log_handler = logging.StreamHandler()
formatter = jsonlogger.JsonFormatter(
    fmt="%(asctime)s %(name)s %(levelname)s %(message)s",
    datefmt="%Y-%m-%dT%H:%M:%S",
)
_log_handler.setFormatter(formatter)
root_logger.addHandler(_log_handler)
root_logger.setLevel(os.getenv("LOG_LEVEL", "INFO"))

# ── FastAPI application ────────────────────────────────────────────────────────
app = FastAPI(
    title="Docker Image Analyzer API",
    version="1.0.0",
    # Disable interactive docs in all environments — not needed for a Lambda API
    docs_url=None,
    redoc_url=None,
    openapi_url=None,
)

app.add_middleware(
    CORSMiddleware,
    allow_origins=[os.getenv("ALLOWED_ORIGIN", "https://imgapp.craftingnewtech.com")],
    allow_methods=["GET", "POST", "OPTIONS"],
    allow_headers=["Content-Type", "Authorization"],
    max_age=3600,
)

app.include_router(analyze.router, prefix="/api/v1", tags=["analyze"])
app.include_router(results.router, prefix="/api/v1", tags=["results"])


@app.get("/api/v1/health")
def health() -> dict:
    return {"status": "ok", "environment": os.getenv("ENVIRONMENT", "unknown")}


# ── Mangum adapter — wraps FastAPI for API Gateway / ALB ──────────────────────
handler = Mangum(app, lifespan="off")
