from __future__ import annotations

from pathlib import Path

from fastapi import FastAPI, Request
from fastapi.staticfiles import StaticFiles
from fastapi.templating import Jinja2Templates

from runtime.web.context import WebContext
from runtime.web.brand import brand_icons_dir, brand_logo_url
from runtime.web.routes import api, pages
from runtime.web.task_fields import TASK_FIELD_OPTIONS
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
    app = FastAPI(title="CapiForge", docs_url=None, redoc_url=None)
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
        css_variables=css_variables_block(),
        brand_logo_url=brand_logo_url(),
        task_field_options=TASK_FIELD_OPTIONS,
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
    return app
