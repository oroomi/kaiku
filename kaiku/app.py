"""Kaiku FastAPI app. Module routers are included when they exist (try/except ImportError)."""
from __future__ import annotations

import asyncio
import importlib
import hmac
import logging
import os
from contextlib import asynccontextmanager
from pathlib import Path

from fastapi import FastAPI, HTTPException, Request
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
from . import demo_contact as _demo_contact  # noqa: E402
app.include_router(_demo_contact.router)

# Module routers: broker, contact, decide, voice, map, learn, mcp_bridge, aura. A missing module is fine.
@app.middleware("http")
async def _persist_chat_sessions(request, call_next):
    response = await call_next(request)
    path = request.url.path
    if path.startswith(("/api/chat", "/api/suggestions", "/webhooks/whatsapp", "/webhooks/call")):
        try:
            from .chat import router as _chat_router
            _chat_router.persist()
        except Exception:
            pass
    return response


for _m in ["broker", "contact", "decide", "voice", "map", "learn", "suggest", "chat", "mcp_bridge", "aura", "score", "listing", "evalpage"]:
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


def _keyed(request: Request) -> bool:
    want = os.environ.get("KAIKU_ROOM_KEY", "")
    qk = request.query_params.get("key", "")
    return events.has_key(request) or bool(want and hmac.compare_digest(qk.encode(), want.encode()))


def _page(request: Request, name: str, **ctx):
    resp = render(request, name, **ctx)
    want = os.environ.get("KAIKU_ROOM_KEY", "")
    qk = request.query_params.get("key", "")
    if want and hmac.compare_digest(qk.encode(), want.encode()):  # keyed laptop: unlock the demo drawer and the decision link
        resp.set_cookie(events.KEY_COOKIE, qk, httponly=True, samesite="lax", max_age=86400,
                        secure=request.headers.get("x-forwarded-proto") == "https")
    return resp


@app.get("/", response_class=HTMLResponse)
@app.get("/owner", response_class=HTMLResponse)
def home(request: Request):
    """The owner's page is one conversation with Kaiku. Demo controls live in a drawer only the key holder gets."""
    return _page(request, "owner.html", business=store.get_business("furry-paw"), owner_view=True)


@app.get("/owner/drawer", response_class=HTMLResponse)
def owner_drawer(request: Request):
    if not _keyed(request):
        raise HTTPException(403, "demo key needed")
    return render(request, "_drawer.html")


@app.get("/judge", response_class=HTMLResponse)
def judge(request: Request):
    k = _keyed(request)
    resp = _page(request, "judge.html", keyed=k)
    if not k:
        resp.status_code = 403
    return resp
