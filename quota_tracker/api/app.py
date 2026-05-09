"""FastAPI app factory and bundled frontend serving."""

from __future__ import annotations

import sys
from pathlib import Path

from fastapi import FastAPI, HTTPException
from fastapi.responses import FileResponse
from fastapi.staticfiles import StaticFiles

from quota_tracker.api.routes import register_routes
from quota_tracker.config import load_config
from quota_tracker.daemon import DaemonService
from quota_tracker.paths import DEFAULT_DB_PATH


def _frontend_dist_path() -> Path:
    """Return bundled frontend assets when packaged, otherwise the repo build directory."""

    bundle_root = getattr(sys, "_MEIPASS", None)
    if bundle_root:
        bundled = Path(str(bundle_root)) / "frontend" / "dist"
        if bundled.exists():
            return bundled
    return Path(__file__).resolve().parents[2] / "frontend" / "dist"


def _mount_frontend(app: FastAPI) -> None:
    """Serve the bundled SPA on all non-/api routes when assets exist."""

    frontend_dist = _frontend_dist_path()
    if not frontend_dist.exists():
        return

    app.mount("/assets", StaticFiles(directory=frontend_dist / "assets"), name="assets")

    @app.get("/")
    def root() -> FileResponse:
        """Serve built frontend index."""

        return FileResponse(frontend_dist / "index.html")

    @app.get("/{full_path:path}")
    def frontend_fallback(full_path: str) -> FileResponse:
        """Serve frontend routes while preserving /api paths."""

        if full_path.startswith("api/"):
            raise HTTPException(status_code=404, detail="not found")
        candidate = frontend_dist / full_path
        if candidate.exists() and candidate.is_file():
            return FileResponse(candidate)
        return FileResponse(frontend_dist / "index.html")


def create_app(
    service: DaemonService | None = None,
    db_path: Path = DEFAULT_DB_PATH,
    config_path: Path | None = None,
) -> FastAPI:
    """Create FastAPI app, optionally wired to a running daemon service."""

    app = FastAPI(title="quota-tracker")
    config_path_str = str(config_path) if config_path is not None else None
    config = load_config(config_path_str)
    register_routes(
        app,
        db_path=db_path,
        config=config,
        config_path_str=config_path_str,
        service=service,
    )
    _mount_frontend(app)
    return app


app = create_app()
