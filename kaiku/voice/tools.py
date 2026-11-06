"""Tools the voice brain may call. Read-only except run_chain (starts the owner-approval chain) and propose_update
(a PROPOSAL; only the owner's tap approves). Every tool returns plain JSON-able dicts and never raises.

Actions: a tool may attach `_actions` (UI hints for the browser). The brain strips them before the model sees the result.
"""
from __future__ import annotations

import asyncio
import json
import logging
import os
import sys
from datetime import date
from pathlib import Path
from typing import Any, Optional

log = logging.getLogger("kaiku.voice.tools")
ROOT = Path(__file__).resolve().parents[2]

HOME = "/"
JUDGE = "/judge"                         # the live event strip and the demo clock live on the judge view
SEL_SUGGESTION = '[data-pilot="hero"]'       # owner.html: the chat thread carries Kaiku's suggestions
SEL_BUSINESS = '[data-pilot="suggestions"]'
SEL_STRIP = '[data-pilot="event-strip"]'
SEL_TODAY = '[data-pilot="today"]'

TOOL_SPECS: list[dict] = [
    {"name": "get_business", "description": "Get a business: name, address, regular opening hours per weekday, last year's holiday exceptions, and the upcoming holidays within 60 days with the hours the business would normally have that day.",
     "input_schema": {"type": "object", "properties": {"business_id": {"type": "string", "description": "e.g. furry-paw"}}, "required": ["business_id"]}},
    {"name": "get_suggestions", "description": "Get Kaiku's holiday-hours suggestions for a business (kind, proposed hours, confidence, reasons, status). If none are stored, returns a read-only preview for the next holiday.",
     "input_schema": {"type": "object", "properties": {"business_id": {"type": "string"}}, "required": ["business_id"]}},
    {"name": "get_events", "description": "Get the latest chain events (detect, suggest, contact, decide, apply, learn), newest last.",
     "input_schema": {"type": "object", "properties": {"limit": {"type": "integer", "description": "1-30, default 10"}}}},
    {"name": "run_chain", "description": "Start the whole chain (detect, suggest, contact the owner, owner decides, apply) for a business and a holiday date. The owner still has the last word.",
     "input_schema": {"type": "object", "properties": {"business_id": {"type": "string"}, "holiday_date": {"type": "string", "description": "YYYY-MM-DD, e.g. 2026-12-24 for Christmas Eve"}}, "required": ["business_id", "holiday_date"]}},
    {"name": "timetravel", "description": "Move Kaiku's clock to a date (YYYY-MM-DD) or 'real'. Returns the new today and the holidays that will be detected within 21 days, with the regular hours that day.",
     "input_schema": {"type": "object", "properties": {"date": {"type": "string"}}, "required": ["date"]}},
    {"name": "get_today", "description": "Get Kaiku's current date (may be a time-travelled date).",
     "input_schema": {"type": "object", "properties": {}}},
]
BROKER_SPECS: list[dict] = [
    {"name": "list_entities", "description": "List entities of an NGSI-LD type in the FIWARE context broker (e.g. Store). Default instance of each attribute.",
     "input_schema": {"type": "object", "properties": {"type": {"type": "string"}, "limit": {"type": "integer"}}, "required": ["type"]}},
    {"name": "get_entity", "description": "Get one broker entity with every source instance (live, Yext, website, last year, proposed) and observedAt.",
     "input_schema": {"type": "object", "properties": {"id": {"type": "string", "description": "e.g. urn:ngsi-ld:Store:furry-paw"}}, "required": ["id"]}},
    {"name": "propose_update", "description": "Write a PROPOSED value for an entity attribute with a reason. It never changes the live value; only the owner can approve.",
     "input_schema": {"type": "object", "properties": {"id": {"type": "string"}, "attr": {"type": "string"}, "value": {}, "reason": {"type": "string"}}, "required": ["id", "attr", "value", "reason"]}},
]


def _spans(h) -> str:
    if h in ("closed", None) or not h:
        return "closed"
    return ", ".join(f"{int(s['start'][:2])}-{int(s['end'][:2])}" if s["start"][3:] == "00" and s["end"][3:] == "00" else f"{s['start']}-{s['end']}" for s in h)


class Tools:
    """Dependencies are injectable so tests run with a fake store, fake chain and fake clock."""

    def __init__(self, store=None, chain=None, clock=None, holidays=None, gateway: Any = "auto"):
        if store is None:
            from .. import store as _s
            store = _s
        if chain is None:
            from .. import chain as _c
            chain = _c
        self.store, self.chain = store, chain
        self.clock = clock or self._clock()
        self.holidays = holidays or self._holidays()
        self._gw = gateway
        self._gw_tried = gateway != "auto"

    # ---- wiring
    @staticmethod
    def _clock():
        try:
            from ..learn import timetravel
            return timetravel
        except Exception:  # noqa: BLE001
            return None

    @staticmethod
    def _holidays():
        try:
            from ..detect import holidays
            return holidays
        except Exception:  # noqa: BLE001
            return None

    @property
    def gateway(self):
        """ngsi-ld-mcp Gateway, or None. Guarded import: voice works without the package. Decisions are never exposed."""
        if not self._gw_tried:
            self._gw_tried = True
            try:
                os.environ.setdefault("NGSI_LD_MCP_HIDE_DECISIONS", "1")
                src = ROOT / "ngsi-ld-mcp" / "src"
                if src.is_dir() and str(src) not in sys.path:
                    sys.path.append(str(src))
                from ngsi_ld_mcp.config import Config
                from ngsi_ld_mcp.core import Gateway
                from ..config import settings
                from ..broker.models import SDM_CONTEXT as _sdm_ctx
                _sdm = lambda: _sdm_ctx  # noqa: E731
                cfg = Config(url=settings.BROKER_URL, hide_decisions=True, context=_sdm())
                self._gw = Gateway(cfg)
            except Exception as e:  # noqa: BLE001
                log.info("ngsi-ld-mcp not available (%s)", type(e).__name__)
                self._gw = None
        return self._gw

    def specs(self) -> list[dict]:
        return TOOL_SPECS + (BROKER_SPECS if self.gateway is not None else [])

    # ---- helpers
    def _today(self) -> date:
        if self.clock is not None:
            return self.clock.today()
        return date.today()

    def _upcoming(self, b: dict, days: int) -> list[dict]:
        if self.holidays is None:
            return []
        out = []
        wd = ["mon", "tue", "wed", "thu", "fri", "sat", "sun"]
        for h in self.holidays.upcoming(self._today(), days):
            d = date.fromisoformat(h.date)
            reg = (b.get("regular_hours") or {}).get(wd[d.weekday()], [])
            ex = next((e for e in b.get("last_year_exceptions", []) if e["date"][5:] == h.date[5:]), None)
            out.append({"date": h.date, "name_fi": h.name_fi, "name_en": h.name_en, "public_holiday": h.public_holiday,
                        "weekday": wd[d.weekday()], "regular_hours_that_day": _spans(reg),
                        "last_year_hours": _spans(ex["hours"]) if ex else "no exception last year"})
        return out

    @staticmethod
    def _sug(s: dict) -> dict:
        return {"id": s["id"], "holiday_date": s["holiday_date"], "kind": s["kind"],
                "proposed_hours": _spans(s["proposed"]) if s.get("proposed") else None, "confidence": s["confidence"],
                "status": s["status"], "reasons_en": [r["text_en"] for r in s.get("reasons", [])],
                "reasons_fi": [r["text_fi"] for r in s.get("reasons", [])],
                "message_fi": s.get("message_fi"), "message_en": s.get("message_en")}

    def _biz(self, bid: str) -> Optional[dict]:
        b = self.store.get_business(bid)
        if b is None:
            return None
        return b.model_dump(mode="json") if hasattr(b, "model_dump") else dict(b)

    # ---- tools
    async def get_business(self, business_id: str = "furry-paw") -> dict:
        b = self._biz(business_id)
        if b is None:
            return {"error": "no such business", "business_id": business_id}
        out = {"id": b["id"], "name": b["name"], "address": b["address"], "regular_hours": {k: _spans(v) for k, v in b["regular_hours"].items()},
               "last_year_exceptions": [{"date": e["date"], "hours": _spans(e["hours"])} for e in b.get("last_year_exceptions", [])],
               "upcoming_holidays": self._upcoming(b, 60), "today": self._today().isoformat(),
               "note": "sample history, fictional; last_year hours are team-written"}
        out["_actions"] = [{"type": "navigate", "url": HOME}, {"type": "spotlight", "selector": SEL_BUSINESS}]
        return out

    async def get_suggestions(self, business_id: str = "furry-paw") -> dict:
        b = self._biz(business_id)
        if b is None:
            return {"error": "no such business", "business_id": business_id}
        rows = self.store.list_suggestions(business_id, 5)
        sugs = [self._sug(s.model_dump(mode="json") if hasattr(s, "model_dump") else s) for s in rows]
        out: dict = {"business_id": business_id, "suggestions": sugs}
        if not sugs:
            out["preview"] = await self._preview(business_id, b)
        out["_actions"] = [{"type": "navigate", "url": HOME}, {"type": "spotlight", "selector": SEL_SUGGESTION}]
        return out

    async def _preview(self, bid: str, b: dict) -> Optional[dict]:
        """Read-only: the registered detect+suggest for the next holiday that differs from regular hours. No events, no storage."""
        try:
            from ..schema import Business
            hs = [h for h in self._upcoming(b, 60) if h["regular_hours_that_day"] != h["last_year_hours"] or h["public_holiday"]]
            if not hs:
                return None
            h = hs[0]["date"]
            bm = self.store.get_business(bid)
            from datetime import datetime, timezone
            det = await self.chain._call(self.chain.STEPS["detect"], bm, h, datetime.now(timezone.utc))
            s = await self.chain._call(self.chain.STEPS["suggest"], bm, det)
            d = self._sug(s.model_dump(mode="json"))
            d["status"] = "preview, not stored"
            return d
        except Exception as e:  # noqa: BLE001
            log.info("preview failed: %s", type(e).__name__)
            return None

    async def get_events(self, limit: int = 10) -> dict:
        n = max(1, min(int(limit or 10), 30))
        ev = self.store.recent_events(n)
        rows = [{"ts": e.ts if isinstance(e.ts, str) else str(e.ts), "step": e.step, "title_fi": e.title_fi, "title_en": e.title_en} for e in ev][-n:]
        return {"events": rows, "_actions": [{"type": "navigate", "url": JUDGE}, {"type": "spotlight", "selector": SEL_STRIP}]}

    async def run_chain(self, business_id: str = "furry-paw", holiday_date: str = "2026-12-24") -> dict:
        try:
            date.fromisoformat(holiday_date)
        except (ValueError, TypeError):
            return {"error": "holiday_date must be YYYY-MM-DD"}
        if self._biz(business_id) is None:
            return {"error": "no such business", "business_id": business_id}
        r = await self.chain.api_run(business=business_id, date=holiday_date)
        sid = r.get("suggestion_id") if isinstance(r, dict) else None
        return {"started": True, "suggestion_id": sid, "business_id": business_id, "holiday_date": holiday_date,
                "note": "chain is running; the owner is asked and has the last word",
                "_actions": [{"type": "navigate", "url": JUDGE}, {"type": "run_chain", "business_id": business_id, "holiday_date": holiday_date, "suggestion_id": sid},
                             {"type": "spotlight", "selector": SEL_STRIP}]}

    async def timetravel(self, date: str = "real") -> dict:  # noqa: A002
        from datetime import date as _d
        if self.clock is None:
            return {"error": "no clock"}
        d = (date or "").strip()
        if d in ("", "real"):
            self.clock.clear()
        else:
            try:
                self.clock.set_today(_d.fromisoformat(d))
            except ValueError:
                return {"error": "date must be YYYY-MM-DD or 'real'"}
        b = self._biz("furry-paw") or {}
        return {"today": self._today().isoformat(), "will_detect_within_21_days": self._upcoming(b, 21),
                "_actions": [{"type": "navigate", "url": JUDGE}, {"type": "spotlight", "selector": SEL_TODAY}]}

    async def get_today(self) -> dict:
        t = self._today()
        return {"today": t.isoformat(), "time_travelled": bool(self.clock and self.clock.is_fake())}

    # ---- broker (through the ngsi-ld-mcp gateway). Agents may only PROPOSE.
    async def list_entities(self, type: str, limit: int = 10) -> dict:  # noqa: A002
        return await self._gw_call("query_entities", type=type, limit=max(1, min(int(limit or 10), 20)))

    async def get_entity(self, id: str) -> dict:  # noqa: A002
        return await self._gw_call("get_entity", id=id)

    async def propose_update(self, id: str, attr: str, value: Any, reason: str) -> dict:  # noqa: A002
        return await self._gw_call("propose_update", id=id, attr=attr, value=value, reason=reason)

    async def _gw_call(self, name: str, **kw) -> dict:
        gw = self.gateway
        if gw is None:
            return {"error": "broker tools unavailable"}
        try:
            r = getattr(gw, name)(**kw)
            return await r if asyncio.iscoroutine(r) else r
        except Exception as e:  # noqa: BLE001
            msg = str(e)
            return {"error": "broker offline or refused", "detail": msg[:200]}

    # ---- dispatch
    async def call(self, name: str, args: dict | None) -> dict:
        args = args or {}
        allowed = {s["name"] for s in self.specs()}
        if name not in allowed:
            return {"error": f"unknown tool {name}"}
        try:
            if name in ("list_entities", "get_entity", "propose_update"):
                return await getattr(self, name)(**args)
            return await getattr(self, name)(**args)
        except TypeError as e:
            return {"error": f"bad arguments: {e}"[:200]}
        except Exception as e:  # noqa: BLE001
            log.warning("tool %s failed: %s", name, type(e).__name__)
            return {"error": f"{name} failed: {type(e).__name__}"}
