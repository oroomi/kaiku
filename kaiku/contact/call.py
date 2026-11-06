"""Contact ladder step 2: Kaiku phones the owner in Finnish (ElevenLabs Conversational AI, native number).

Transport is injectable (same shape as whatsapp.Transport) so tests never touch the network.
Secrets come from .env and are never printed or logged. See docs/call.md for the assumptions made about the API.
"""
from __future__ import annotations

import json
import os
import sys
import tempfile
from datetime import datetime, timezone
from pathlib import Path
from typing import Callable

from . import messages as M
from . import whatsapp as W

BASE = "https://api.elevenlabs.io"
MAX_MONTHLY_PRICE = 10.0
Transport = W.Transport

FIRST_MESSAGE = "Hei, täällä Kaiku, Fonecta Connectin avustaja. Soitan yrityksenne aukioloajoista, onko hetki aikaa?"
FIRST_MESSAGE_EN = "Hello, this is Kaiku, Fonecta Connect's assistant. I am calling about your opening hours, do you have a moment?"

SYSTEM_PROMPT = """Olet Kaiku, Fonecta Connectin avustaja. Soitat yrityksen {{business_name}} omistajalle. Puhu vain suomea, rauhallisesti, enintään kaksi lausetta kerrallaan.
Tiedot, joita saat käyttää (älä keksi mitään muuta):
- pyhäpäivä: {{holiday_name_fi}}, {{holiday_date_fi}}
- ehdotetut aukioloajat: {{proposed_hours}}
- viime vuoden ajat: {{last_year}}
- peruste: {{reason}}
Kulku:
1. Kun omistaja on vastannut ensimmäiseen kysymykseen, kerro kahdella lauseella: {{holiday_name_fi}} on {{holiday_date_fi}} ja ehdotat aukioloajaksi {{proposed_hours}}, koska {{reason}}.
2. Kysy: "Hyväksytkö?"
3. Jos omistaja sanoo kyllä, hyväksyn, joo tai vastaavaa: sano "Kiitos, päivitän tiedot nyt. Näkyy pian Googlessa ja muissa kanavissa." ja lopeta puhelu.
4. Jos omistaja antaa muut ajat (esimerkiksi "yhdeksästä yhteen", "9-13", "suljettu"): toista ajat takaisin ja kysy "Oliko oikein?". Kun hän vahvistaa, kiitä ja lopeta puhelu.
5. Jos omistaja sanoo ei: sano "Selvä, en muuta mitään. Kiitos ajastasi." ja lopeta puhelu.
6. Jos omistaja ei ymmärrä tai kysyy jotain muuta, vastaa vain yllä olevien tietojen perusteella. Jos et tiedä, sano ettet tiedä, ja kysy uudelleen: "Hyväksytkö?"
Älä koskaan lupaa mitään, mitä et saa tiedoista. Älä pyydä henkilötietoja. Lopeta puhelu kohteliaasti."""

# English gloss of the script is in docs/call.md.

DATA_COLLECTION = {
    "action": {"type": "string",
               "description": "Omistajan päätös: approve (hyväksyi ehdotetut ajat), edit (antoi muut ajat tai sanoi suljettu), decline (ei muutosta), none (ei päätöstä)."},
    "hours": {"type": "string",
              "description": "Jos action on edit: omistajan antamat ajat muodossa HH:MM-HH:MM, tai 'closed' jos suljettu. Muuten tyhjä."},
}


# ------------------------------------------------------------------ env helpers

def get_key() -> str:
    W.load_env()
    return os.environ.get("ELEVENLABS_API_KEY", "")


def set_env(name: str, value: str, path: Path | None = None) -> None:
    """Atomic .env update (replace line or append), chmod 600; also sets os.environ. Value is never printed."""
    p = Path(path) if path else W.env_path()
    try:
        lines = p.read_text(encoding="utf-8").splitlines()
    except OSError:
        lines = []
    out, done = [], False
    for ln in lines:
        if ln.split("=", 1)[0].strip() == name:
            if not done:
                out.append(f"{name}={value}")
            done = True
        else:
            out.append(ln)
    if not done:
        out.append(f"{name}={value}")
    fd, tmp = tempfile.mkstemp(dir=str(p.parent), prefix=".env.")
    with os.fdopen(fd, "w", encoding="utf-8") as f:
        f.write("\n".join(out) + "\n")
    os.chmod(tmp, 0o600)
    os.replace(tmp, p)
    os.environ[name] = value


def _now() -> str:
    return datetime.now(timezone.utc).strftime("%Y-%m-%dT%H:%M:%SZ")


class Api:
    def __init__(self, key: str | None = None, transport: Transport | None = None):
        self.key = key if key is not None else get_key()
        self.transport = transport or W.httpx_transport

    def call(self, method: str, path: str, payload: dict | None = None) -> tuple[int, dict]:
        try:
            return self.transport(method, BASE + path, {"xi-api-key": self.key, "Content-Type": "application/json"}, payload)
        except Exception as e:  # network errors never leak headers
            return 0, {"error": type(e).__name__}


def _err(status: int, body: dict) -> str:
    d = body.get("detail") if isinstance(body, dict) else None
    if isinstance(d, dict):
        d = d.get("message") or d.get("status")
    return f"HTTP {status}: {str(d or body.get('error') or body.get('raw') or '')[:160]}"


# ------------------------------------------------------------------ setup: webhook, agent, number

def webhook_url() -> str:
    W.load_env()
    return (os.environ.get("PUBLIC_URL") or "http://127.0.0.1:8210").rstrip("/") + "/webhooks/call"


def ensure_webhook(api: Api | None = None) -> dict:
    """Workspace HMAC webhook for post-call transcription. Stores ELEVENLABS_WEBHOOK_ID and ELEVENLABS_WEBHOOK_SECRET."""
    api = api or Api()
    W.load_env()
    if os.environ.get("ELEVENLABS_WEBHOOK_ID") and os.environ.get("ELEVENLABS_WEBHOOK_SECRET"):
        return {"ok": True, "webhook_id": os.environ["ELEVENLABS_WEBHOOK_ID"], "created": False}
    st, b = api.call("POST", "/v1/workspace/webhooks",
                     {"settings": {"auth_type": "hmac", "name": "kaiku-call", "webhook_url": webhook_url()}})
    if st >= 300 or not b.get("webhook_id"):
        return {"ok": False, "error": _err(st, b)}
    set_env("ELEVENLABS_WEBHOOK_ID", b["webhook_id"])
    if b.get("webhook_secret"):
        set_env("ELEVENLABS_WEBHOOK_SECRET", b["webhook_secret"])
    # Make it the post-call webhook for transcripts (assumed endpoint, best effort).
    api.call("PATCH", "/v1/convai/settings", {"webhooks": {"post_call_webhook_id": b["webhook_id"], "events": ["transcript"]}})
    return {"ok": True, "webhook_id": b["webhook_id"], "created": True}


def agent_payload(voice_id: str, webhook_id: str | None = None) -> dict:
    p = {
        "name": "Kaiku (Connect call)",
        "conversation_config": {
            "agent": {
                "language": "fi",
                "first_message": FIRST_MESSAGE,
                "prompt": {"prompt": SYSTEM_PROMPT, "llm": "gemini-2.0-flash", "temperature": 0.2},
                "dynamic_variables": {"dynamic_variable_placeholders": {
                    "business_name": "yrityksenne", "holiday_name_fi": "pyhäpäivä", "holiday_date_fi": "24.12.",
                    "proposed_hours": "9-13", "last_year": "ei tietoa", "reason": "viime vuonna oli samat ajat"}},
            },
            "tts": {"voice_id": voice_id, "model_id": "eleven_flash_v2_5"},
            "conversation": {"max_duration_seconds": 240},
        },
        "platform_settings": {
            "data_collection": DATA_COLLECTION,
            "overrides": {"conversation_config_override": {"agent": {"first_message": True, "language": False}}},
        },
    }
    if webhook_id:
        p["platform_settings"]["workspace_overrides"] = {"webhooks": {"post_call_webhook_id": webhook_id}}
    return p


def ensure_agent(api: Api | None = None) -> dict:
    api = api or Api()
    W.load_env()
    if os.environ.get("ELEVENLABS_AGENT_ID"):
        return {"ok": True, "agent_id": os.environ["ELEVENLABS_AGENT_ID"], "created": False}
    voice = os.environ.get("ELEVENLABS_VOICE_ID", "")
    if not voice:
        return {"ok": False, "error": "ELEVENLABS_VOICE_ID missing"}
    st, b = api.call("POST", "/v1/convai/agents/create", agent_payload(voice, os.environ.get("ELEVENLABS_WEBHOOK_ID")))
    if st >= 300 or not b.get("agent_id"):
        return {"ok": False, "error": _err(st, b)}
    set_env("ELEVENLABS_AGENT_ID", b["agent_id"])
    return {"ok": True, "agent_id": b["agent_id"], "created": True}


def _price(item: dict):
    for k in ("monthly_price", "monthly_cost", "price_per_month", "price"):
        v = item.get(k)
        if isinstance(v, dict):
            v = v.get("amount", v.get("value"))
        if v is not None:
            try:
                return float(v)
            except (TypeError, ValueError):
                return None
    return None


def ensure_phone_number(api: Api | None = None, max_price: float = MAX_MONTHLY_PRICE, country: str = "US") -> dict:
    """Use an existing account number; else buy a native one only if monthly cost is known and < max_price (0 counts as free).
    Any purchase additionally requires KAIKU_ALLOW_NUMBER_PURCHASE=1 (the owner's explicit yes after seeing the price)."""
    api = api or Api()
    W.load_env()
    if os.environ.get("ELEVENLABS_PHONE_NUMBER_ID"):
        return {"ok": True, "phone_number_id": os.environ["ELEVENLABS_PHONE_NUMBER_ID"], "created": False}
    st, b = api.call("GET", "/v1/convai/phone-numbers")
    if st >= 300:
        return {"ok": False, "error": _err(st, b)}
    items = b if isinstance(b, list) else b.get("phone_numbers", b.get("items", []))
    if items:
        pid = items[0].get("phone_number_id")
        set_env("ELEVENLABS_PHONE_NUMBER_ID", pid)
        return {"ok": True, "phone_number_id": pid, "created": False}
    # ASSUMED endpoints (not in public docs): search then purchase.
    st, b = api.call("GET", f"/v1/convai/phone-numbers/available?country={country}")
    if st in (404, 405):
        return {"ok": False, "reason": "native purchase API not found; buy a number in the ElevenLabs dashboard (Agents > Phone numbers) and rerun setup"}
    if st >= 300:
        return {"ok": False, "error": _err(st, b)}
    avail = b if isinstance(b, list) else b.get("phone_numbers", b.get("items", []))
    priced = [(p, _price(x)) for x in avail for p in [x]]
    ok = [(x, p) for x, p in priced if p is not None and p < max_price]
    if not ok:
        known = [p for _, p in priced if p is not None]
        return {"ok": False, "reason": f"no number under {max_price:g} per month; cheapest {min(known):g}" if known
                else "price unknown, not buying"}
    x, p = min(ok, key=lambda t: t[1])
    if os.environ.get("KAIKU_ALLOW_NUMBER_PURCHASE") != "1":
        return {"ok": False, "reason": f"purchase needs the owner's yes: cheapest {p:g} per month; set KAIKU_ALLOW_NUMBER_PURCHASE=1 and rerun"}
    st, b = api.call("POST", "/v1/convai/phone-numbers/purchase", {"phone_number": x.get("phone_number"), "label": "Kaiku"})
    if st >= 300 or not b.get("phone_number_id"):
        return {"ok": False, "error": _err(st, b)}
    set_env("ELEVENLABS_PHONE_NUMBER_ID", b["phone_number_id"])
    return {"ok": True, "phone_number_id": b["phone_number_id"], "created": True, "monthly_price": p}


def setup(api: Api | None = None) -> dict:
    api = api or Api()
    r = {"webhook": ensure_webhook(api)}
    r["agent"] = ensure_agent(api)
    r["phone"] = ensure_phone_number(api)
    r["ok"] = all(v.get("ok") for v in r.values())
    return r


# ------------------------------------------------------------------ placing calls

def log_path() -> Path:
    return W.data_dir() / "call_log.jsonl"


def _log(rec: dict) -> None:
    rec = {"at": _now(), **rec}
    try:
        with open(log_path(), "a", encoding="utf-8") as f:
            f.write(json.dumps(rec, ensure_ascii=False) + "\n")
    except OSError:
        pass


def _hours_text(v) -> str:
    v = M._hours_of(v)
    return "ei tietoa" if v is None else M.fi_hours(v)


def dynamic_variables(s: dict) -> dict:
    reasons = s.get("reasons") or []
    reason = ""
    if reasons:
        r0 = reasons[0]
        reason = r0.get("text_fi", "") if isinstance(r0, dict) else str(r0)
    return {
        "business_name": M.business_name(s),
        "holiday_name_fi": M.holiday_name(s).lower() if M._has_name(s) else "pyhäpäivä",
        "holiday_date_fi": M.fi_date(s["holiday_date"]),
        "proposed_hours": M.fi_hours(s.get("proposed")),
        "last_year": _hours_text(M._last_year(s)),
        "reason": (reason or "viime vuoden ajat olivat samat").rstrip("."),
        "suggestion_id": str(s.get("id", "")),
        "business_id": str(s.get("business_id", "")),
    }


def outbound_payload(s: dict, to_number: str, agent_id: str, phone_id: str) -> dict:
    dv = dynamic_variables(s)
    return {"agent_id": agent_id, "agent_phone_number_id": phone_id, "to_number": "+" + W.normalize_phone(to_number),
            "conversation_initiation_client_data": {
                "user_id": dv["suggestion_id"],
                "dynamic_variables": dv,
                "source_info": {"source": "kaiku", "version": dv["suggestion_id"]}},
            "telephony_call_config": {"ringing_timeout_secs": 30}}


def place_call(suggestion: dict, to_number: str | None = None, api: Api | None = None) -> dict:
    """Start an outbound call. to_number defaults to the demo owner phone (OWNER_WHATSAPP). Never raises."""
    W.load_env()
    agent_id, phone_id = os.environ.get("ELEVENLABS_AGENT_ID"), os.environ.get("ELEVENLABS_PHONE_NUMBER_ID")
    sid = suggestion.get("id")
    if not (agent_id and phone_id):
        _log({"suggestion_id": sid, "ok": False, "reason": "call lane not configured"})
        return {"ok": False, "reason": "call lane not configured"}
    to = to_number or os.environ.get("OWNER_WHATSAPP") or suggestion.get("owner_whatsapp")
    if not W.normalize_phone(to):
        return {"ok": False, "reason": "no recipient number"}
    api = api or Api()
    st, b = api.call("POST", "/v1/convai/twilio/outbound-call", outbound_payload(suggestion, to, agent_id, phone_id))
    if st >= 300 or not b.get("success", True) or not b.get("conversation_id"):
        err = b.get("message") if isinstance(b, dict) and b.get("message") else _err(st, b)
        _log({"suggestion_id": sid, "ok": False, "error": err})
        return {"ok": False, "error": err}
    _log({"suggestion_id": sid, "business_id": suggestion.get("business_id"), "ok": True,
          "conversation_id": b["conversation_id"], "to_tail": W.normalize_phone(to)[-4:]})
    try:
        from kaiku import events  # type: ignore
        events.emit(events.Event(ts=_now(), step="contact", business_id=suggestion.get("business_id"), suggestion_id=sid,
                                 title_fi="Puhelu: Kaiku soittaa omistajalle", title_en="Call: Kaiku is phoning the owner",
                                 detail={"conversation_id": b["conversation_id"]}))
    except Exception:
        pass
    return {"ok": True, "conversation_id": b["conversation_id"]}


def suggestion_for_conversation(conversation_id: str) -> dict:
    """Fallback lookup from call_log.jsonl when the webhook lacks our dynamic variables."""
    try:
        for ln in reversed(log_path().read_text(encoding="utf-8").splitlines()):
            r = json.loads(ln)
            if r.get("conversation_id") == conversation_id:
                return r
    except (OSError, ValueError):
        pass
    return {}


# ------------------------------------------------------------------ CLI

def status() -> dict:
    W.load_env()
    keys = ["ELEVENLABS_API_KEY", "ELEVENLABS_VOICE_ID", "ELEVENLABS_AGENT_ID", "ELEVENLABS_PHONE_NUMBER_ID",
            "ELEVENLABS_WEBHOOK_ID", "ELEVENLABS_WEBHOOK_SECRET", "PUBLIC_URL"]
    out = {k: bool(os.environ.get(k)) for k in keys}  # booleans only, never values
    out["webhook_url"] = webhook_url()
    out["ready"] = all(out[k] for k in ("ELEVENLABS_API_KEY", "ELEVENLABS_AGENT_ID", "ELEVENLABS_PHONE_NUMBER_ID"))
    return out


def main(argv: list[str] | None = None) -> int:
    import argparse
    ap = argparse.ArgumentParser(prog="python -m kaiku.contact.call")
    sub = ap.add_subparsers(dest="cmd", required=True)
    sub.add_parser("setup")
    sub.add_parser("status")
    c = sub.add_parser("call")
    c.add_argument("--to", required=True)
    c.add_argument("--suggestion", required=True)
    a = ap.parse_args(argv)
    if a.cmd == "status":
        print(json.dumps(status(), indent=1))
        return 0
    if a.cmd == "setup":
        r = setup()
        print(json.dumps(r, indent=1))  # ids only
        return 0 if r["ok"] else 2
    s = json.loads(Path(a.suggestion).read_text(encoding="utf-8"))
    s = s.get("suggestion", s)
    r = place_call(s, a.to)
    print(json.dumps(r, indent=1))
    return 0 if r.get("ok") else 2


if __name__ == "__main__":
    sys.exit(main())
