"""FastAPI v3 — billing, API keys, orgs + enhanced analyze routes."""

import logging
import os

from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware
from mangum import Mangum
from pythonjsonlogger import jsonlogger

from .routers import analyze, api_keys, billing, orgs, results

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

app = FastAPI(
    title="DocImgAnalizer API v3",
    version="3.0.0",
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
    allow_headers=["Content-Type", "Authorization", "X-Api-Key"],
    max_age=3600,
)

app.include_router(analyze.router, prefix="/api/v3")
app.include_router(results.router, prefix="/api/v3")
app.include_router(billing.router, prefix="/api/v3")
app.include_router(api_keys.router, prefix="/api/v3")
app.include_router(orgs.router, prefix="/api/v3")


@app.get("/api/v3/health")
def health() -> dict:
    return {"status": "ok", "version": "3", "environment": _env}


handler = Mangum(app, lifespan="off")
