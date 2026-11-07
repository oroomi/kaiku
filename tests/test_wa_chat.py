"""WhatsApp is the same conversation as the website chat: one text opening, any reply goes to the chat brain, decisions run
through the chat's own path. Fakes only: no WhatsApp, email, Anthropic or Yext call leaves this file."""
import asyncio
import json
import os

import pytest

from kaiku import chain, store
from kaiku.chat import brain, feed as chat_feed, router as chat_router
from kaiku.contact import ladder as L
from kaiku.contact import messages as M
from kaiku.contact import router as R
from kaiku.contact import whatsapp as W

PHONE = "358401234567"
FEED = {"suggestions": [
    {"id": "t-hours", "kind": "holiday_hours", "title_en": "Christmas Eve 24.12. hours are missing",
     "text_en": "Last year you were open 9-13. Connect still publishes 9-17.", "proposed": [{"start": "09:00", "end": "13:00"}],
     "confidence": 0.8, "status": "proposed", "holiday_date": "2026-12-24", "holiday_name_en": "Christmas Eve",
     "last_year": [{"start": "09:00", "end": "13:00"}], "reasons": [{"source": "last_year", "text_en": "Last year 9-13"}]},
    {"id": "t-nochange", "kind": "no_change", "title_en": "Father's Day 8.11.",
     "text_en": "Father's Day 8.11. is not a public holiday and you are closed on Sundays. Nothing to change.", "proposed": None,
     "confidence": 0.95, "status": "proposed", "holiday_date": "2026-11-08", "reasons": []},
]}
SUG = {"id": "t-hours", "business_id": "furry-paw", "business_name": "Furry Paw Vet Clinic", "holiday_date": "2026-12-24",
       "holiday_name_fi": "Jouluaatto", "holiday_name_en": "Christmas Eve", "kind": "hours",
       "proposed": [{"start": "09:00", "end": "13:00"}], "last_year_hours": [{"start": "09:00", "end": "13:00"}],
       "google_now": [{"start": "09:00", "end": "17:00"}], "channel_log": []}


@pytest.fixture(autouse=True)
def isolated(tmp_path, monkeypatch):
    """Nothing real: empty WA creds, no SMTP, no .env, no Anthropic key, a private DB and data dir, a fake feed."""
    from kaiku.config import settings
    from kaiku.learn import timetravel
    for k in ("WA_TOKEN", "WA_PHONE_ID", "ANTHROPIC_API_KEY", "WA_BUTTONS", "WA_TEMPLATE_NAME", "WA_TEMPLATE_NAME_EN", "WA_APP_SECRET"):
        monkeypatch.setenv(k, "")
    monkeypatch.setenv("KAIKU_NO_SMTP", "1")
    monkeypatch.setenv("KAIKU_ENV", "/nonexistent/.env")
    monkeypatch.setenv("KAIKU_DATA_DIR", str(tmp_path))
    monkeypatch.setenv("OWNER_WHATSAPP", "+358 40 123 4567")
    monkeypatch.setenv("KAIKU_CHAT_NO_LLM", "1")
    timetravel.clear()
    old_db = settings.DB_PATH
    store.reset(tmp_path / "wa.sqlite")
    store.seed()
    chat_router._sessions.clear()
    W.set_client(None)

    def live(bid, *a, **k):  # the chat feed takes network=... now
        d = json.loads(json.dumps(FEED))
        for it in d["suggestions"]:
            s = store.get_suggestion(it["id"])
            if s:
                it["status"] = {"approved": "approved", "edited": "approved", "applied": "approved", "declined": "declined"}.get(s.status, "proposed")
        return d
    monkeypatch.setattr(chat_feed, "get_feed", live)
    yield
    L.cancel_pending()
    W.set_client(None)
    store.reset(old_db)


class Fake:
    def __init__(self, responses=None):
        self.calls, self.responses = [], list(responses or [])

    def __call__(self, method, url, headers, payload):
        self.calls.append((method, url, headers, payload))
        return self.responses.pop(0) if self.responses else (200, {"messages": [{"id": f"wamid.{len(self.calls)}"}]})

    def texts(self):
        return [c[3]["text"]["body"] for c in self.calls if c[3].get("type") == "text"]


def client(fake):
    # a configured client around a FAKE transport: the empty env creds never reach Meta
    return W.WhatsAppClient(token="TOK", phone_id="123", transport=fake)


@pytest.fixture
def fake_yext(monkeypatch):
    writes = []

    def backend(entity_id, day, proposed):
        writes.append((entity_id, day, proposed))
        return {"yext_status": "ok", "verified": True, "entity_id": entity_id, "written": proposed}
    monkeypatch.setattr(chain, "apply_backend", backend)
    monkeypatch.setattr(chain, "whatsapp_configured", lambda: False)
    return writes


def run(c):
    return asyncio.run(c)


def inbound(body, mid="wamid.IN1"):
    return {"entry": [{"changes": [{"value": {"messages": [{"from": PHONE, "id": mid, "timestamp": "1", "type": "text",
                                                            "text": {"body": body}}]}}]}]}


def button(bid, mid="wamid.B1"):
    return {"entry": [{"changes": [{"value": {"messages": [{"from": PHONE, "id": mid, "timestamp": "1", "type": "interactive",
                                                            "interactive": {"type": "button_reply", "button_reply": {"id": bid, "title": "x"}}}]}}]}]}


def start(monkeypatch=None):
    """Ladder step as the chain runs it, without email."""
    L.E.owner_email = lambda s: ""
    f = Fake()
    L.contact(dict(SUG, channel_log=[]), client=client(f), escalate_s=10**6)
    return f


# ---------------------------------------------------------------- 1. the ladder message

def test_ladder_sends_one_interactive_opener_with_accept_and_discard(monkeypatch):
    monkeypatch.setattr(L.E, "owner_email", lambda s: "")
    f = Fake()
    s = dict(SUG, channel_log=[])
    L.contact(s, client=client(f), escalate_s=10**6)
    assert len(f.calls) == 1
    p = f.calls[0][3]
    assert p["type"] == "interactive" and p["to"] == PHONE
    btns = p["interactive"]["action"]["buttons"]
    assert [b["reply"]["title"] for b in btns] == ["Accept", "Discard"]          # exactly two buttons
    assert [b["reply"]["id"] for b in btns] == ["approve:t-hours", "decline:t-hours"]
    body = p["interactive"]["body"]["text"]
    assert body.startswith("Hi Furry Paw Vet Clinic!")  # one item, a warm hand-over question
    assert "9-13" in body and "—" not in body
    assert body.endswith("Tap Accept to save it or Discard to leave it. To change the hours, just reply with them.")
    assert "Just reply yes" not in body
    assert s["status"] == "sent" and s["channel_log"][0]["channel"] == "whatsapp"


def test_ladder_sends_one_plain_text_when_wa_buttons_is_zero(monkeypatch):
    monkeypatch.setattr(L.E, "owner_email", lambda s: "")
    monkeypatch.setenv("WA_BUTTONS", "0")
    f = Fake()
    L.contact(dict(SUG, channel_log=[]), client=client(f), escalate_s=10**6)
    assert len(f.calls) == 1
    p = f.calls[0][3]
    assert p["type"] == "text" and "interactive" not in p
    body = p["text"]["body"]
    assert body.startswith("Hi Furry Paw Vet Clinic!") and "9-13" in body
    assert body.endswith("Just reply yes, or tell me what the hours should be, and I'll take care of the rest.") and "Tap Accept" not in body


def test_ladder_template_path_outside_window_then_buttons_follow_the_reply(monkeypatch):
    monkeypatch.setattr(L.E, "owner_email", lambda s: "")
    f = Fake([(400, {"error": {"code": 131047, "message": "x"}}), (200, {"messages": [{"id": "wamid.T"}]}), (200, {"messages": [{"id": "wamid.X"}]})])
    L.contact(dict(SUG, channel_log=[]), client=client(f), escalate_s=10**6)
    assert f.calls[0][3]["type"] == "interactive" and f.calls[1][3]["type"] == "template"
    # the owner answers the template: the same warm opener arrives with Accept / Discard
    run(R.handle_payload(inbound("hei", "wamid.IN0"), client(f)))
    sent = [c[3] for c in f.calls if c[3].get("status") != "read"]       # a read receipt is not a message
    assert [m["type"] for m in sent] == ["interactive", "template", "interactive"]
    p = sent[2]["interactive"]
    assert [b["reply"]["title"] for b in p["action"]["buttons"]] == ["Accept", "Discard"]
    assert p["body"]["text"].startswith("Hi Furry Paw Vet Clinic!") and p["body"]["text"].endswith("just reply with them.")
    assert f.texts() == []


def test_ladder_no_change_stays_plain(monkeypatch):
    monkeypatch.setattr(L.E, "owner_email", lambda s: "")
    f = Fake()
    L.contact(dict(SUG, id="t-nochange", kind="no_change", channel_log=[]), client=client(f), escalate_s=10**6)
    assert "Just reply yes, or tell me what the hours should be" not in json.dumps(f.calls[0][3])


# ---------------------------------------------------------------- 2. inbound text -> the brain

def test_inbound_text_goes_to_the_brain_and_back_as_text(monkeypatch):
    seen = []

    async def fake_respond(bid, sess, message):
        seen.append((bid, sess, message))
        return "Sure, it is 9-13.", []
    monkeypatch.setattr(brain, "respond", fake_respond)
    R.register_sent(PHONE, "t-hours", None, "furry-paw")
    f = Fake()
    res = run(R.handle_payload(inbound("what hours did you suggest?", "wamid.A"), client(f)))
    assert seen[0][0] == "furry-paw" and seen[0][2] == "what hours did you suggest?"
    assert f.texts() == ["Sure, it is 9-13."] and res["replies"] == 1
    # the second message from the same phone continues the same session
    run(R.handle_payload(inbound("and the reason?", "wamid.B"), client(f)))
    assert seen[1][1] is seen[0][1] and chat_router._sessions["wa:" + PHONE] is seen[0][1]
    assert seen[0][1]["hist"][:2] == [("user", "what hours did you suggest?"), ("assistant", "Sure, it is 9-13.")]
    assert seen[0][1]["via"] == "whatsapp"


def test_stranger_phone_is_not_answered(monkeypatch):
    async def boom(*a, **k):
        raise AssertionError("brain must not be called")
    monkeypatch.setattr(brain, "respond", boom)
    p = inbound("hello")
    p["entry"][0]["changes"][0]["value"]["messages"][0]["from"] = "358999999999"
    f = Fake()
    res = run(R.handle_payload(p, client(f)))
    assert f.texts() == [] and res["ignored"] == 1


# ---------------------------------------------------------------- 3. approval = the web chat's decision path

def test_whatsapp_approval_runs_the_web_chat_path(fake_yext, monkeypatch):
    R.register_sent(PHONE, "t-hours", None, "furry-paw")
    f = Fake()
    res = run(R.handle_payload(inbound("yes", "wamid.Y"), client(f)))
    assert fake_yext == [("SinceAI07", "2026-12-24", [{"start": "09:00", "end": "13:00"}])]
    assert store.get_decisions("t-hours")[0].via == "whatsapp" and store.get_suggestion("t-hours").status == "applied"
    ev = [e for e in store.recent_events(50) if e.suggestion_id == "t-hours"]
    assert any(e.step == "decide" and (e.detail or {}).get("via") == "whatsapp" for e in ev) and any(e.step == "apply" for e in ev)
    body = f.texts()[0]
    assert body.startswith("Done. 24.12. 9-13 is saved and shows on Google, Fonecta Finder and 020202 within the hour.")
    assert body.endswith("You changed this last year as well. Do you want to make it recurring, this time of the year?")
    assert res["decisions"][0]["action"] == "approve"
    # standing permission: yes to the follow-up, same tool as the web chat
    run(R.handle_payload(inbound("yes", "wamid.Y2"), client(f)))
    assert len(fake_yext) == 1
    from kaiku.learn import prefs
    assert prefs.get_prefs("furry-paw")["standing_permission"]["holiday"] == "christmaseve"


def test_whatsapp_edit_new_times(fake_yext):
    R.register_sent(PHONE, "t-hours", None, "furry-paw")
    f = Fake()
    run(R.handle_payload(inbound("make it 10-14", "wamid.E"), client(f)))
    assert fake_yext[-1][2] == [{"start": "10:00", "end": "14:00"}]
    assert store.get_decisions("t-hours")[0].via == "whatsapp" and store.get_decisions("t-hours")[0].action == "edit"


def test_waiting_chain_run_gets_on_decision_first(fake_yext, monkeypatch):
    got = []

    async def on_decision(d):
        got.append(d)
        s = store.get_suggestion(d["suggestion_id"]) or __import__("kaiku.chat.actions", fromlist=["x"]).materialize("furry-paw", FEED["suggestions"][0])
        s.status = "applied"
        store.save_suggestion(s)
        return True
    monkeypatch.setattr(chain, "on_decision", on_decision)
    R.register_sent(PHONE, "t-hours", None, "furry-paw")
    run(R.handle_payload(inbound("yes", "wamid.W"), client(Fake())))
    assert got and got[0]["via"] == "whatsapp" and got[0]["action"] == "approve" and fake_yext == []


def test_decline_on_whatsapp(fake_yext):
    R.register_sent(PHONE, "t-hours", None, "furry-paw")
    f = Fake()
    run(R.handle_payload(inbound("no thanks", "wamid.N"), client(f)))
    assert fake_yext == [] and store.get_suggestion("t-hours").status == "declined"
    assert store.get_decisions("t-hours")[0].via == "whatsapp" and "leave it" in f.texts()[0]


# ---------------------------------------------------------------- 4. fallback parser

def test_brain_failure_falls_back_to_the_keyword_parser(fake_yext, monkeypatch):
    async def boom(*a, **k):
        raise RuntimeError("brain down")
    monkeypatch.setattr(brain, "respond", boom)
    R.register_sent(PHONE, "t-hours", None, "furry-paw")
    res = run(R.handle_payload(inbound("yes", "wamid.F"), client(Fake())))
    assert res["decisions"][0]["action"] == "approve" and res["decisions"][0]["via"] == "whatsapp"
    assert fake_yext == [("SinceAI07", "2026-12-24", [{"start": "09:00", "end": "13:00"}])]
    f = Fake()
    run(R.handle_payload(inbound("banana", "wamid.F2"), client(f)))  # not understood: never silent
    assert f.texts() == [M.unknown_reply_text(None)]


def test_no_api_key_uses_the_keyword_parser_inside_the_brain(fake_yext, monkeypatch):
    monkeypatch.delenv("KAIKU_CHAT_NO_LLM", raising=False)
    monkeypatch.setenv("ANTHROPIC_API_KEY", "")
    R.register_sent(PHONE, "t-hours", None, "furry-paw")
    f = Fake()
    run(R.handle_payload(inbound("9 to 1", "wamid.K"), client(f)))
    assert fake_yext[-1][2] == [{"start": "09:00", "end": "13:00"}] and f.texts()


# ---------------------------------------------------------------- 5. buttons still work

def test_approve_tap_applies_at_once_and_replies_with_the_receipt(fake_yext):
    R.register_sent(PHONE, "t-hours", "wamid.OUT", "furry-paw")
    f = Fake()
    res = run(R.handle_payload(button("approve:t-hours"), client(f)))
    assert res["decisions"][0]["suggestion_id"] == "t-hours"
    assert fake_yext == [("SinceAI07", "2026-12-24", [{"start": "09:00", "end": "13:00"}])]   # one tap applied it
    assert store.get_decisions("t-hours")[0].via == "whatsapp" and store.get_suggestion("t-hours").status == "applied"
    assert f.texts()[0].startswith("Done. 24.12. 9-13 is saved and shows on Google, Fonecta Finder and 020202 within the hour.")


def test_edit_button_then_text_and_decline_button(fake_yext):
    R.register_sent(PHONE, "t-hours", "wamid.OUT", "furry-paw")
    f = Fake()
    res = run(R.handle_payload(button("edit:t-hours"), client(f)))
    assert res["edit_requested"] == ["t-hours"] and f.texts() == [M.edit_prompt_text(None)]
    run(R.handle_payload(inbound("10-14", "wamid.T"), client(f)))
    assert fake_yext[-1][2] == [{"start": "10:00", "end": "14:00"}]
    R.register_sent(PHONE, "t-hours", "wamid.OUT2", "furry-paw")


def test_decline_tap_declines_via_whatsapp_and_kaiku_says_leave_it(fake_yext):
    R.register_sent(PHONE, "t-hours", "wamid.OUT", "furry-paw")
    f = Fake()
    run(R.handle_payload(button("decline:t-hours"), client(f)))
    assert store.get_suggestion("t-hours").status == "declined" and fake_yext == []
    assert store.get_decisions("t-hours")[0].action == "decline" and store.get_decisions("t-hours")[0].via == "whatsapp"
    assert f.texts() == ["Okay, I leave it as it is."]                   # Kaiku's own line, not the legacy thank-you text
    assert M.decline_thanks_text(None) not in f.texts()


def test_status_log_untouched(tmp_path):
    st = {"entry": [{"changes": [{"value": {"statuses": [{"id": "wamid.OUT", "status": "delivered", "timestamp": "1", "recipient_id": PHONE}]}}]}]}
    run(R.handle_payload(st, client(Fake())))
    assert "delivered" in (tmp_path / "wa_status.jsonl").read_text()


def test_period_item_does_not_break_the_chat_opening():
    from kaiku.chat.util import hours_text
    period = [{"date": "2026-12-24", "proposed": [{"start": "09:00", "end": "13:00"}]}, {"date": "2026-12-25", "proposed": "closed"}]
    assert hours_text(period) == "24.12. 9-13; 25.12. closed"


# ---------------------------------------------------------------- 7. one WhatsApp thread: a chain-run id, "let me think", then "yes"; the ladder's call is cancelled

def _chain_run_suggestion(sid="chain-x"):
    from kaiku.schema import Suggestion
    return Suggestion.model_validate({"id": sid, "business_id": "furry-paw", "holiday_date": "2026-12-24", "kind": "hours",
                                      "proposed": [{"start": "09:00", "end": "13:00"}], "confidence": 0.75, "reasons": [],
                                      "message_fi": "", "message_en": "", "status": "sent", "channel_log": []})


def test_think_then_yes_on_a_chain_run_id_goes_through_the_brain(fake_yext):
    """The ladder registers the chain run's own id; the brain must still answer (mapped to the feed card by date)."""
    store.save_suggestion(_chain_run_suggestion())
    R.register_sent(PHONE, "chain-x", None, "furry-paw")
    f = Fake()
    run(R.handle_payload(inbound("Uhmm let me think", "wamid.T1"), client(f)))
    first = f.texts()[-1]
    assert "Tap one of the buttons" not in first and "did not understand" not in first
    assert fake_yext == []  # thinking is not a decision
    run(R.handle_payload(inbound("yes", "wamid.T2"), client(f)))
    assert fake_yext and store.get_suggestion("t-hours").status in ("approved", "applied")
    assert store.get_decisions("t-hours")[0].via == "whatsapp"


def test_whatsapp_yes_cancels_the_ladder_call(fake_yext, monkeypatch):
    import sys, types
    called = []
    mod = types.ModuleType("kaiku.contact.call"); mod.place_call = lambda s: (called.append(s["id"]), {"ok": True, "conversation_id": "conv_fake"})[1]
    monkeypatch.setitem(sys.modules, "kaiku.contact.call", mod)
    monkeypatch.setattr(L.E, "owner_email", lambda s: "")
    store.save_suggestion(_chain_run_suggestion("chain-y"))
    s = dict(SUG, id="chain-y", channel_log=[])
    f = Fake()
    L.contact(s, client=client(f), escalate_s=0.6)  # WhatsApp text out, the call is armed for 0.6 s
    run(R.handle_payload(inbound("yes", "wamid.T3"), client(f)))  # the owner approves on WhatsApp
    import time
    time.sleep(1.2)
    assert called == [], "the call must never be placed after a WhatsApp approval"
    assert fake_yext
