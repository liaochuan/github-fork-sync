from pathlib import Path

from fastapi import FastAPI
from fastapi.staticfiles import StaticFiles

from gfs.config import Settings
from gfs.web.routes import TokenManager, create_router


def create_app(settings: Settings | None = None) -> FastAPI:
    if settings is None:
        settings = Settings.from_env()

    app = FastAPI(title="GitHub Fork Sync")
    app.state.settings = settings
    app.state.token_manager = TokenManager()

    app.include_router(create_router(settings, app.state.token_manager))

    static_dir = Path(__file__).parent / "static"
    app.mount("/static", StaticFiles(directory=str(static_dir)), name="static")

    return app
