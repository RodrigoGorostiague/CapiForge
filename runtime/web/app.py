from __future__ import annotations

import asyncio
from contextlib import asynccontextmanager
from pathlib import Path

from fastapi import FastAPI, Request
from fastapi.staticfiles import StaticFiles
from fastapi.templating import Jinja2Templates

from runtime.events.change_watcher import ChangeWatcher
from runtime.events.db_paths import resolve_web_db_paths
from runtime.events.notify import set_event_bus
from runtime.version import __version__
from runtime.web.brand import brand_icons_dir, brand_logo_url
from runtime.web.context import WebContext
from runtime.web.routes import api, events, pages
from runtime.web.task_fields import TASK_FIELD_OPTIONS
from runtime.web.i18n import audit_count_label
from runtime.web.theme import (
    css_variables_block,
    pill_class_for_audit_state,
    pill_class_for_effort,
    pill_class_for_priority,
    pill_class_for_risk,
    pill_class_for_task_state,
    pill_class_for_task_type,
    pill_label,
)


def _web_root() -> Path:
    return Path(__file__).resolve().parent


def create_app(ctx: WebContext) -> FastAPI:
    watcher: ChangeWatcher | None = None
    watcher_task: asyncio.Task | None = None

    @asynccontextmanager
    async def lifespan(app: FastAPI):
        nonlocal watcher, watcher_task
        if ctx.realtime_enabled:
            watcher = ChangeWatcher()
            set_event_bus(watcher.bus)
            db_paths = resolve_web_db_paths(ctx.repo_root, ctx.node_home)
            watcher_task = asyncio.create_task(watcher.run(db_paths))
            app.state.event_bus = watcher.bus
            app.state.change_watcher = watcher
        else:
            set_event_bus(None)
            app.state.event_bus = None
            app.state.change_watcher = None
        yield
        if watcher is not None:
            watcher.stop()
        if watcher_task is not None:
            watcher_task.cancel()
            try:
                await watcher_task
            except asyncio.CancelledError:
                pass
        set_event_bus(None)

    app = FastAPI(title="CapiForge", docs_url=None, redoc_url=None, lifespan=lifespan)
    templates = Jinja2Templates(directory=str(_web_root() / "templates"))
    static_dir = _web_root() / "static"
    app.mount("/static", StaticFiles(directory=str(static_dir)), name="static")
    icons_dir = brand_icons_dir()
    if icons_dir is not None:
        app.mount("/brand", StaticFiles(directory=str(icons_dir)), name="brand")

    @app.middleware("http")
    async def attach_context(request: Request, call_next):
        request.state.web_ctx = ctx
        request.state.templates = templates
        response = await call_next(request)
        return response

    templates.env.globals.update(
        app_version=__version__,
        css_variables=css_variables_block(),
        brand_logo_url=brand_logo_url(),
        task_field_options=TASK_FIELD_OPTIONS,
        audit_count_label=audit_count_label,
        pill_label=pill_label,
        pill_class_for_task_state=pill_class_for_task_state,
        pill_class_for_priority=pill_class_for_priority,
        pill_class_for_effort=pill_class_for_effort,
        pill_class_for_risk=pill_class_for_risk,
        pill_class_for_task_type=pill_class_for_task_type,
        pill_class_for_audit_state=pill_class_for_audit_state,
    )

    app.include_router(pages.router)
    app.include_router(api.router, prefix="/api")
    app.include_router(events.router, prefix="/api")
    return app
