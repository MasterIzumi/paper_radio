"""FastAPI app for the local Paper Radio dashboard."""
from __future__ import annotations

from pathlib import Path

from dotenv import load_dotenv
load_dotenv()

from fastapi import FastAPI
from fastapi.staticfiles import StaticFiles

from server.deep_analysis_api import collection_router as deep_analysis_collection_router
from server.deep_analysis_api import router as deep_analysis_router
from server.favorites_api import router as favorites_router
from server.jobs_api import router as jobs_router
from server.reports_api import router as reports_router
from storage.db import init_db

app = FastAPI(title="Paper Radio Dashboard")


@app.on_event("startup")
def on_startup() -> None:
    init_db()


@app.get("/api/health")
def health():
    return {"ok": True}


app.include_router(reports_router)
app.include_router(jobs_router)
app.include_router(deep_analysis_router)
app.include_router(deep_analysis_collection_router)
app.include_router(favorites_router)

WEBAPP_DIR = Path("webapp")
if WEBAPP_DIR.exists():
    app.mount("/", StaticFiles(directory=str(WEBAPP_DIR), html=True), name="webapp")
