"""Meta WhatsApp Cloud API client (Graph API v21.0). Transport is injectable so tests never touch the network.

Secrets (WA_TOKEN, WA_PHONE_ID, ...) come from /root/hack/kaiku/.env via python-dotenv and are never logged or printed.
"""
from __future__ import annotations

import json
import os
import time
from pathlib import Path
from typing import Callable

GRAPH_VERSION = "v21.0"
GRAPH_BASE = "https://graph.facebook.com"
ROOT = Path(__file__).resolve().parents[2]
CANONICAL_ENV = Path("/root/hack/kaiku/.env")

DEFAULT_BUTTONS = [("approve", "Hyväksy"), ("edit", "Muokkaa"), ("decline", "Ei kiitos")]

ERR_OUTSIDE_WINDOW = 131047
ERR_NOT_ALLOWED = 131030
ERR_RE_ENGAGEMENT = 131051  # unsupported message type; kept for completeness


def data_dir() -> Path:
    d = Path(os.environ.get("KAIKU_DATA_DIR") or ROOT / "data")
    d.mkdir(parents=True, exist_ok=True)
    return d


def env_path() -> Path:
    for p in (Path(os.environ["KAIKU_ENV"]) if os.environ.get("KAIKU_ENV") else None, ROOT / ".env", CANONICAL_ENV):
        if p and p.exists():
            return p
    return CANONICAL_ENV


def load_env() -> None:
    try:
        from dotenv import load_dotenv
        load_dotenv(env_path(), override=False)
    except ImportError:  # pragma: no cover
        pass


def normalize_phone(p: str | None) -> str:
    """Graph API wants digits only, country code first: '+358 40 123' -> '35840123'."""
    return "".join(c for c in (p or "") if c.isdigit())


Transport = Callable[[str, str, dict, dict | None], tuple[int, dict]]


def httpx_transport(method: str, url: str, headers: dict, payload: dict | None) -> tuple[int, dict]:
    import httpx
    r = httpx.request(method, url, headers=headers, json=payload, timeout=20)
    try:
        return r.status_code, r.json()
    except ValueError:
        return r.status_code, {"raw": r.text[:300]}


class WhatsAppClient:
    def __init__(self, token: str | None = None, phone_id: str | None = None, transport: Transport | None = None,
                 log_path: Path | None = None):
        load_env()
        self.token = token if token is not None else os.environ.get("WA_TOKEN", "")
        self.phone_id = phone_id if phone_id is not None else os.environ.get("WA_PHONE_ID", "")
        self.transport = transport or httpx_transport
        self.log_path = log_path

    @property
    def configured(self) -> bool:
        return bool(self.token and self.phone_id)

    # ---- payload builders (pure) ----
    @staticmethod
    def text_payload(to: str, body: str) -> dict:
        return {"messaging_product": "whatsapp", "recipient_type": "individual", "to": normalize_phone(to),
                "type": "text", "text": {"preview_url": False, "body": body}}

    @staticmethod
    def buttons_payload(to: str, body: str, buttons: list[tuple[str, str]] | None = None) -> dict:
        buttons = buttons or DEFAULT_BUTTONS
        if not 1 <= len(buttons) <= 3:
            raise ValueError("WhatsApp reply buttons: 1 to 3")
        for bid, title in buttons:
            if len(title) > 20:
                raise ValueError(f"button title over 20 chars: {title!r}")
        if len(body) > 1024:
            raise ValueError("interactive body over 1024 chars")
        return {"messaging_product": "whatsapp", "recipient_type": "individual", "to": normalize_phone(to),
                "type": "interactive",
                "interactive": {"type": "button", "body": {"text": body},
                                "action": {"buttons": [{"type": "reply", "reply": {"id": bid, "title": title}}
                                                        for bid, title in buttons]}}}

    @staticmethod
    def template_payload(to: str, name: str = "hello_world", lang: str = "en_US") -> dict:
        return {"messaging_product": "whatsapp", "to": normalize_phone(to), "type": "template",
                "template": {"name": name, "language": {"code": lang}}}

    # ---- sending ----
    def _url(self, path: str = "messages") -> str:
        return f"{GRAPH_BASE}/{GRAPH_VERSION}/{self.phone_id}/{path}"

    def _post(self, payload: dict, kind: str, path: str = "messages") -> dict:
        if not self.configured:
            res = {"ok": False, "error": "WA_TOKEN / WA_PHONE_ID not set", "blocked": True}
            self._log(kind, payload, res)
            return res
        headers = {"Authorization": f"Bearer {self.token}", "Content-Type": "application/json"}
        try:
            status, body = self.transport("POST", self._url(path), headers, payload)
        except Exception as e:  # network failure
            res = {"ok": False, "error": f"transport error: {type(e).__name__}"}
            self._log(kind, payload, res)
            return res
        res = self.map_response(status, body)
        self._log(kind, payload, res)
        return res

    @staticmethod
    def map_response(status: int, body: dict) -> dict:
        if 200 <= status < 300 and not body.get("error"):
            msgs = body.get("messages") or []
            return {"ok": True, "message_id": msgs[0].get("id") if msgs else None, "status": status}
        err = body.get("error") or {}
        code = err.get("code")
        sub = (err.get("error_data") or {}).get("details") or err.get("message", "")
        res = {"ok": False, "status": status, "code": code, "error": str(sub)[:300]}
        if code == ERR_OUTSIDE_WINDOW:
            res["needs_template"] = True
            res["error"] = "Outside the 24 h customer service window: send a template first (the customer's reply reopens the window)."
        elif code == ERR_NOT_ALLOWED:
            res["error"] = ("Recipient phone number is not in the allowed list of the test number. Add it under "
                            "WhatsApp > API Setup > To in the Meta developer console and confirm the OTP.")
        elif code == 190:
            res["error"] = "Access token invalid or expired (test tokens last 24 h unless a system user token is used)."
        return res

    def send_text(self, to: str, body: str) -> dict:
        return self._post(self.text_payload(to, body), "text")

    def send_buttons(self, to: str, body: str, buttons: list[tuple[str, str]] | None = None) -> dict:
        return self._post(self.buttons_payload(to, body, buttons), "buttons")

    def send_template(self, to: str, name: str = "hello_world", lang: str = "en_US") -> dict:
        return self._post(self.template_payload(to, name, lang), "template")

    def mark_read(self, message_id: str) -> dict:
        return self._post({"messaging_product": "whatsapp", "status": "read", "message_id": message_id}, "read")

    # ---- log, never contains the token ----
    def _log(self, kind: str, payload: dict, res: dict) -> None:
        try:
            p = self.log_path or data_dir() / "wa_sends.jsonl"
            rec = {"at": time.strftime("%Y-%m-%dT%H:%M:%SZ", time.gmtime()), "kind": kind,
                   "to_tail": normalize_phone(payload.get("to"))[-4:], "result": res,
                   "preview": (payload.get("text", {}).get("body") or payload.get("interactive", {}).get("body", {}).get("text")
                               or payload.get("template", {}).get("name") or "")[:80]}
            with open(p, "a", encoding="utf-8") as f:
                f.write(json.dumps(rec, ensure_ascii=False) + "\n")
        except OSError:
            pass


_default: WhatsAppClient | None = None


def get_client() -> WhatsAppClient:
    global _default
    if _default is None:
        _default = WhatsAppClient()
    return _default


def set_client(c: WhatsAppClient | None) -> None:
    global _default
    _default = c


def send_text(to, body): return get_client().send_text(to, body)
def send_buttons(to, body, buttons=None): return get_client().send_buttons(to, body, buttons)
def send_template(to, name="hello_world", lang="en_US"): return get_client().send_template(to, name, lang)
def mark_read(message_id): return get_client().mark_read(message_id)
