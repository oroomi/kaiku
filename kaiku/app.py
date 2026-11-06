"""Kaiku FastAPI app. Module routers are included when they exist (try/except ImportError)."""
from __future__ import annotations

import importlib
import logging
from contextlib import asynccontextmanager
from pathlib import Path

from fastapi import FastAPI, Request
from fastapi.responses import HTMLResponse
from fastapi.staticfiles import StaticFiles
from fastapi.templating import Jinja2Templates

from . import chain, events, store
from .config import settings

log = logging.getLogger("kaiku")
WEB = Path(__file__).parent / "web"
templates = Jinja2Templates(directory=str(WEB / "templates"))


@asynccontextmanager
async def lifespan(app: FastAPI):
    store.seed()
    yield


app = FastAPI(title="Kaiku", lifespan=lifespan)


class NoCacheStatic(StaticFiles):
    """Cloudflare would otherwise cache css/js for hours; pages add ?v=<mtime> to bust it."""
    async def get_response(self, path, scope):
        r = await super().get_response(path, scope)
        r.headers["Cache-Control"] = "no-cache"
        return r


def asset_v() -> str:
    try:
        return str(int(max(p.stat().st_mtime for p in (WEB / "static").iterdir() if p.is_file())))
    except ValueError:
        return "0"


templates.env.globals["asset_v"] = asset_v
app.mount("/static", NoCacheStatic(directory=str(WEB / "static")), name="static")
app.include_router(events.router)
app.include_router(chain.router)

# Module routers: broker, contact, decide, voice, map, learn, mcp_bridge, aura. A missing module is fine.
for _m in ["broker", "contact", "decide", "voice", "map", "learn", "mcp_bridge", "aura"]:
    try:
        app.include_router(importlib.import_module(f"kaiku.{_m}.router").router)
    except ImportError:
        try:  # also accept kaiku/<module>/__init__.py exposing `router`
            app.include_router(importlib.import_module(f"kaiku.{_m}").router)
        except (ImportError, AttributeError):
            log.info("module %s not present", _m)


def render(request: Request, name: str, **ctx):
    ctx.setdefault("public_url", settings.PUBLIC_URL)
    return templates.TemplateResponse(request, name, ctx)


@app.get("/healthz")
def healthz():
    return {"ok": True, "broker": "unknown"}


@app.get("/", response_class=HTMLResponse)
def home(request: Request):
    b = store.get_business("furry-paw")
    return render(request, "home.html", business=b)
