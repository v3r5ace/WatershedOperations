import asyncio

from fastapi import FastAPI
from fastapi.staticfiles import StaticFiles
from starlette.middleware.sessions import SessionMiddleware

from app.config import get_settings
from app.database import Base, SessionLocal, engine
from app.routers.api import router as api_router
from app.routers.ui import router as ui_router
from app.seed import seed_defaults
from app.services.calendar import sync_calendar_from_url


settings = get_settings()
settings.database_path.parent.mkdir(parents=True, exist_ok=True)
Base.metadata.create_all(bind=engine)

with SessionLocal() as db:
    seed_defaults(db)

app = FastAPI(title=settings.app_name)
app.add_middleware(
    SessionMiddleware,
    secret_key=settings.secret_key,
    session_cookie=settings.session_cookie_name,
    same_site="lax",
    https_only=False,
)

app.mount("/static", StaticFiles(directory="app/static"), name="static")
app.include_router(ui_router)
app.include_router(api_router)


async def run_calendar_sync_once() -> None:
    if not settings.calendar_ics_url:
        return

    with SessionLocal() as db:
        await sync_calendar_from_url(db, settings.calendar_ics_url)


async def calendar_sync_worker() -> None:
    while True:
        try:
            await run_calendar_sync_once()
        except Exception:
            # Keep the worker alive even if one sync attempt fails.
            pass
        await asyncio.sleep(3600)


@app.on_event("startup")
async def startup_sync_calendar() -> None:
    await run_calendar_sync_once()
    app.state.calendar_sync_task = asyncio.create_task(calendar_sync_worker())


@app.on_event("shutdown")
async def shutdown_sync_calendar() -> None:
    task = getattr(app.state, "calendar_sync_task", None)
    if not task:
        return
    task.cancel()
    try:
        await task
    except asyncio.CancelledError:
        pass


@app.get("/healthz")
def healthcheck():
    return {"status": "ok"}
