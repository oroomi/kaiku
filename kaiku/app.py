"""Kaiku FastAPI app. Module routers are included when they exist (try/except ImportError)."""
from __future__ import annotations

import asyncio
import importlib
import hmac
import logging
import os
from contextlib import asynccontextmanager
from pathlib import Path

from fastapi import FastAPI, Request
from fastapi.responses import HTMLResponse
from fastapi.staticfiles import StaticFiles
from fastapi.templating import Jinja2Templates

from . import chain, events, store
from .config import settings

log = logging.getLogger("kaiku")
for _n in ("httpx", "httpcore"):  # their INFO lines carry full URLs, including api_key= query strings
    logging.getLogger(_n).setLevel(logging.WARNING)
WEB = Path(__file__).parent / "web"
templates = Jinja2Templates(directory=str(WEB / "templates"))


@asynccontextmanager
async def lifespan(app: FastAPI):
    store.seed()
    try:  # FIWARE spine: entity with holidayHoursStatus, then the two standing subscriptions. Never blocks start-up.
        await asyncio.to_thread(chain.broker_seed, "furry-paw")
        from .broker.subs import ensure_subscriptions
        await asyncio.to_thread(ensure_subscriptions)
    except Exception as exc:
        log.warning("broker start-up: %s", exc)
    from .mcp_bridge import running as _mcp_running
    async with _mcp_running():
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
for _m in ["broker", "contact", "decide", "voice", "map", "learn", "suggest", "chat", "mcp_bridge", "aura"]:
    try:
        app.include_router(importlib.import_module(f"kaiku.{_m}.router").router)
    except ImportError:
        try:  # also accept kaiku/<module>/__init__.py exposing `router`
            app.include_router(importlib.import_module(f"kaiku.{_m}").router)
        except (ImportError, AttributeError):
            log.info("module %s not present", _m)


try:
    from .mcp_bridge import install as _install_mcp
    _install_mcp(app, "/mcp")
except Exception as _e:  # pragma: no cover
    log.info("mcp bridge: %s", _e)

try:  # importing the ladder registers its dict-based contact step; core then re-registers the Suggestion adapter
    import kaiku.contact.ladder  # noqa: F401
except Exception as _e:  # pragma: no cover
    log.info("contact ladder not importable: %s", _e)
chain.register("contact", chain.contact_step)


def render(request: Request, name: str, **ctx):
    ctx.setdefault("public_url", settings.PUBLIC_URL)
    return templates.TemplateResponse(request, name, ctx)


@app.get("/healthz")
def healthz():
    try:
        broker = chain.get_broker().name
    except Exception:
        broker = "fallback"
    return {"ok": True, "broker": broker}


@app.get("/", response_class=HTMLResponse)
def home(request: Request):
    b = store.get_business("furry-paw")
    resp = render(request, "home.html", business=b)
    want = os.environ.get("KAIKU_ROOM_KEY", "")
    qk = request.query_params.get("key", "")
    if want and hmac.compare_digest(qk.encode(), want.encode()):  # keyed laptop: unlock the decision link for this browser
        resp.set_cookie(events.KEY_COOKIE, qk, httponly=True, samesite="lax", max_age=86400,
                        secure=request.headers.get("x-forwarded-proto") == "https")
    return resp
