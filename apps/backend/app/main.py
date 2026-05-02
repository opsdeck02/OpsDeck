import asyncio

from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware

from app.api.v1.router import api_router
from app.core.config import settings
from app.core.security_middleware import SecurityMiddleware
from app.modules.tenants.scheduler import scheduler_loop

app = FastAPI(
    title=settings.app_name,
    debug=settings.app_debug,
    version="0.1.0",
)

app.add_middleware(SecurityMiddleware)
app.add_middleware(
    CORSMiddleware,
    allow_origins=settings.cors_origins,
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

app.include_router(api_router, prefix=settings.api_v1_prefix)


@app.on_event("startup")
async def start_scheduler() -> None:
    app.state.scheduler_stop_event = asyncio.Event()
    app.state.scheduler_task = asyncio.create_task(
        scheduler_loop(app.state.scheduler_stop_event)
    )


@app.on_event("shutdown")
async def stop_scheduler() -> None:
    stop_event = getattr(app.state, "scheduler_stop_event", None)
    task = getattr(app.state, "scheduler_task", None)
    if stop_event is not None:
        stop_event.set()
    if task is not None:
        await task


@app.get("/", tags=["root"])
def root() -> dict[str, str]:
    return {"message": "SteelOps Control Tower API"}
