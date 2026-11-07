"""Contact channel preference: the last question of every conversation ("how do you want me to reach you next time?"),
on the email decision page, on WhatsApp and in the web chat (one flow), and the ladder that honours the answer.
Fakes only: no WhatsApp, email, call or Anthropic request leaves this file."""
import json
import os

os.environ.setdefault("OWNER_WHATSAPP", "+358000000000")  # settings are read at first import (same as test_core)

import pytest
from fastapi.testclient import TestClient

from kaiku import store
from kaiku.chat import flow
from kaiku.contact import ladder as L
from kaiku.contact import messages as M
from kaiku.contact import router as R
from kaiku.learn import prefs
from test_wa_chat import (PHONE, SUG, Fake, button, client, fake_yext, inbound, isolated, run)  # noqa: F401

BID = "furry-paw"


def _events():
    return store.recent_events(200)


def _kinds(f):
    return [c[3].get("type") for c in f.calls if c[3].get("type") in ("text", "interactive")]


def _last_interactive(f):
    return [c[3] for c in f.calls if c[3].get("type") == "interactive"][-1]


def _titles_ids(payload):
    return [(b["reply"]["id"], b["reply"]["title"]) for b in payload["interactive"]["action"]["buttons"]]


def _decide_on_whatsapp(f, fake_yext_writes=None):
    R.register_sent(PHONE, "t-hours", "wamid.OUT", BID)
    run(R.handle_payload(button("approve:t-hours"), client(f)))


@pytest.fixture
def no_recurring(monkeypatch):
    """A decision with no last-year data: no recurring question, so the channel question follows the receipt at once."""
    from kaiku.chat import actions as A
    monkeypatch.setattr(A, "has_last_year", lambda bid, item: False)


QUESTION = "Next time something about your listing needs a decision, how do you want me to reach you?"


# ---------------------------------------------------------------- preference store

def test_store_get_set_and_learn_event(tmp_path):
    assert prefs.get_contact_channel(BID) is None
    prefs.set_contact_channel(BID, "whatsapp", said="WhatsApp please")
    assert prefs.get_contact_channel(BID) == "whatsapp"
    assert json.loads((tmp_path / "learn_prefs.json").read_text())[BID]["contact_channel"] == "whatsapp"
    ev = [e for e in _events() if e.step == "learn"]
    assert ev[-1].title_en == "Learned: prefers WhatsApp next time" and ev[-1].detail["said"] == "WhatsApp please"
    with pytest.raises(ValueError):
        prefs.set_contact_channel(BID, "sms")


@pytest.mark.parametrize("text,want", [("email", "email"), ("WhatsApp", "whatsapp"), ("call", "call"), ("Call me", "call"),
                                       ("by whatsapp!", "whatsapp"), ("sms", None), ("yes", None), ("email or call", None),
                                       ("", None), ("sähköposti", "email")])
def test_parse_channel(text, want):
    assert prefs.parse_channel(text) == want


def test_reset_with_learn_clears_it(tmp_path):
    prefs.set_contact_channel(BID, "call")
    from kaiku.app import app
    c = TestClient(app)
    r = c.post("/api/reset?learn=1&key=testkey")
    assert r.status_code == 200
    assert prefs.get_contact_channel(BID) is None


# ---------------------------------------------------------------- WhatsApp: asked after the decision, answered by tap or typing

def test_whatsapp_asks_after_a_decision_with_three_buttons(fake_yext, no_recurring):
    f = Fake()
    _decide_on_whatsapp(f)
    p = _last_interactive(f)
    assert _titles_ids(p) == [("pref:email", "Email"), ("pref:whatsapp", "WhatsApp"), ("pref:call", "Call")]
    body = p["interactive"]["body"]["text"]
    assert body.startswith("Done.") and QUESTION in body and "—" not in body


def test_whatsapp_question_is_plain_text_with_a_reply_line_when_buttons_are_off(fake_yext, monkeypatch, no_recurring):
    monkeypatch.setenv("WA_BUTTONS", "0")
    f = Fake()
    _decide_on_whatsapp(f)
    assert "interactive" not in _kinds(f)
    last = f.texts()[-1]
    assert QUESTION in last and last.endswith("Just reply email, WhatsApp or call.")


def test_tap_on_pref_whatsapp_stores_and_confirms(fake_yext, no_recurring):
    f = Fake()
    _decide_on_whatsapp(f)
    n = len(f.calls)
    run(R.handle_payload(button("pref:whatsapp", "wamid.P1"), client(f)))
    assert prefs.get_contact_channel(BID) == "whatsapp"
    new = [c[3]["text"]["body"] for c in f.calls[n:] if c[3].get("type") == "text"]
    assert new == ["Got it, WhatsApp it is. I'll start there next time."]


def test_typed_call_stores_call(fake_yext, no_recurring):
    f = Fake()
    _decide_on_whatsapp(f)
    run(R.handle_payload(inbound("call", "wamid.P2"), client(f)))
    assert prefs.get_contact_channel(BID) == "call"
    assert f.texts()[-1] == "Got it, a call it is. I'll start there next time."


def test_unrelated_reply_gets_the_warm_text_once_and_the_question_is_dropped(fake_yext, no_recurring):
    f = Fake()
    _decide_on_whatsapp(f)
    run(R.handle_payload(inbound("sms", "wamid.P3"), client(f)))
    assert prefs.get_contact_channel(BID) is None
    assert f.texts()[-1] == M.channel_unknown_text_en() and "—" not in f.texts()[-1]
    n = len(f.calls)
    run(R.handle_payload(inbound("call", "wamid.P4"), client(f)))     # the question is gone: a later 'call' stores nothing
    assert prefs.get_contact_channel(BID) is None
    assert f.texts()[-1] != M.channel_unknown_text_en() and "interactive" not in _kinds(f)[-1:]   # warm text once, never nagged


def test_not_asked_again_once_answered(fake_yext, no_recurring):
    prefs.set_contact_channel(BID, "email")
    f = Fake()
    _decide_on_whatsapp(f)
    assert "interactive" not in _kinds(f)


def test_asked_after_the_recurring_answer(fake_yext):
    """When the recurring-permission question was asked, the channel question waits for its answer."""
    f = Fake()
    try:
        _decide_on_whatsapp(f)
        assert "interactive" not in _kinds(f) and "recurring" in f.texts()[-1]
        run(R.handle_payload(inbound("yes", "wamid.R1"), client(f)))
    finally:
        pass
    p = _last_interactive(f)
    assert QUESTION in p["interactive"]["body"]["text"] and p["interactive"]["body"]["text"].startswith("Every Christmas Eve")


# ---------------------------------------------------------------- web chat: same flow, reply chips

def test_web_chat_offers_chips_after_accept_and_stores_the_typed_answer(fake_yext, no_recurring):
    from kaiku.app import app
    from kaiku.chat import router as CR
    c = TestClient(app)
    r = c.post("/api/suggestions/t-hours/accept", json={"business_id": BID, "session": "web1"}).json()
    assert r["ok"] and QUESTION in r["reply"]
    assert [x["value"] for x in r["choices"]] == ["email", "whatsapp", "call"]
    r2 = c.post("/api/chat", json={"business_id": BID, "session": "web1", "message": "WhatsApp"}).json()
    assert r2["reply"] == "Got it, WhatsApp it is. I'll start there next time." and r2["choices"] == []
    assert prefs.get_contact_channel(BID) == "whatsapp"


# ---------------------------------------------------------------- decision page

@pytest.fixture()
def page(tmp_path, monkeypatch):
    monkeypatch.setenv("PUBLIC_URL", "http://test")
    from kaiku.schema import Reason, Span, Suggestion
    s = Suggestion(id="sgc1", business_id=BID, holiday_date="2026-12-24", kind="hours", proposed=[Span(start="09:00", end="13:00")],
                   confidence=0.9, reasons=[Reason(source="last_year", dataset_id="x", text_fi="Viime jouluaattona olitte auki 9-13.",
                                                   text_en="Last Christmas Eve you were open 9-13.")])
    store.save_suggestion(s)
    from kaiku.app import app
    from kaiku.decide import step, tokens
    step._waiting.clear()
    return TestClient(app), tokens.issue(s.id, s.business_id)


def test_decision_page_holds_the_question_and_the_endpoint_stores_it(page, fake_yext):
    c, tok = page
    html = c.get("/d/" + tok).text
    assert QUESTION in html and 'data-channel="email"' in html and 'data-channel="whatsapp"' in html and 'data-channel="call"' in html
    r = c.post(f"/api/decide/{tok}/channel", json={"channel": "whatsapp"})
    assert r.status_code == 409                                             # the decision comes first
    assert c.post(f"/api/decide/{tok}", json={"action": "approve"}).status_code == 200
    assert QUESTION in c.get("/d/" + tok).text and "hidden" not in c.get("/d/" + tok).text.split('id="chpref"')[1].split(">")[0]
    r = c.post(f"/api/decide/{tok}/channel", json={"channel": "whatsapp"})
    assert r.status_code == 200 and r.json()["message"] == "Got it, WhatsApp it is. I'll start there next time."
    assert prefs.get_contact_channel(BID) == "whatsapp"
    assert c.post(f"/api/decide/{tok}/channel", json={"channel": "sms"}).status_code == 422
    assert c.post("/api/decide/nope/channel", json={"channel": "call"}).status_code == 404


# ---------------------------------------------------------------- the ladder honours it

class FakeTimer:
    made = []

    def __init__(self, delay, fn, args=()):
        self.delay, self.fn, self.args, self.cancelled, self.daemon = delay, fn, args, False, True
        FakeTimer.made.append(self)

    def start(self): pass
    def cancel(self): self.cancelled = True
    def fire(self): return self.fn(*self.args)


class FakeWA:
    def __init__(self): self.sent = []
    def send_buttons(self, phone, body, btns): self.sent.append("buttons"); return {"ok": True, "message_id": "w1"}
    def send_text(self, phone, body): self.sent.append("text"); return {"ok": True, "message_id": "w1"}


@pytest.fixture
def ladder(monkeypatch):
    import sys
    import types
    FakeTimer.made = []
    monkeypatch.setattr(L, "_timer_factory", FakeTimer)
    monkeypatch.setenv("OWNER_EMAIL", "owner@example.com")
    monkeypatch.setenv("OWNER_WHATSAPP", "+358401234567")
    called = []
    mod = types.ModuleType("kaiku.contact.call")
    mod.place_call = lambda s: (called.append(s["id"]), {"ok": True})[1]
    monkeypatch.setitem(sys.modules, "kaiku.contact.call", mod)
    import kaiku.contact as pkg
    monkeypatch.setattr(pkg, "call", mod, raising=False)
    monkeypatch.setattr(R, "is_decided", lambda sid: False)
    monkeypatch.setattr(L.E, "send_decision_email", lambda s, to: (called.append("email"), {"ok": True, "dry_run": True, "path": "x"})[1])
    return called


def _chan(s):
    return [c["channel"] for c in s["channel_log"]]


def test_ladder_whatsapp_first_then_email_then_call(ladder):
    prefs.set_contact_channel(BID, "whatsapp")
    wa, s = FakeWA(), dict(SUG, id="lw1", channel_log=[])
    L.contact(s, client=wa, escalate_s=50, email_escalate_s=20)
    assert wa.sent == ["buttons"] and ladder == []                       # WhatsApp went out first, email did not
    assert s["channel_log"][0]["channel"] == "whatsapp"
    assert any(e.title_en == "Reaching the owner by WhatsApp first (their preference)" for e in _events())
    FakeTimer.made[-1].fire()                                            # no decision: email next
    assert ladder == ["email"] and "email" in _chan(s)
    FakeTimer.made[-1].fire()                                            # then the call
    assert ladder == ["email", "lw1"] and _chan(s)[-1] == "call"


def test_ladder_call_first_then_whatsapp_then_email(ladder):
    prefs.set_contact_channel(BID, "call")
    wa, s = FakeWA(), dict(SUG, id="lc1", channel_log=[])
    L.contact(s, client=wa, escalate_s=50, email_escalate_s=20)
    assert ladder == ["lc1"] and wa.sent == []
    FakeTimer.made[-1].fire()
    assert wa.sent == ["buttons"] and ladder == ["lc1"]
    FakeTimer.made[-1].fire()
    assert ladder == ["lc1", "email"]
    assert ladder.count("lc1") == 1                                      # the call is not repeated


def test_ladder_email_preference_keeps_todays_order(ladder):
    prefs.set_contact_channel(BID, "email")
    wa, s = FakeWA(), dict(SUG, id="le1", channel_log=[])
    L.contact(s, client=wa, escalate_s=50, email_escalate_s=20)
    assert ladder == ["email"] and wa.sent == []
    FakeTimer.made[-1].fire()
    assert wa.sent == ["buttons"]


def test_preferred_call_still_obeys_no_call(monkeypatch):
    """The call rung is call.place_call: KAIKU_NO_CALL=1 (tests) and outbound_allowed keep it silent even when preferred."""
    from kaiku.contact import call
    prefs.set_contact_channel(BID, "call")
    monkeypatch.setattr(L.E, "owner_email", lambda s: "")
    monkeypatch.setattr(L, "_timer_factory", FakeTimer)
    FakeTimer.made = []
    monkeypatch.setenv("OWNER_WHATSAPP", "+358401234567")
    s = dict(SUG, id="ln1", channel_log=[])
    L.contact(s, client=FakeWA(), escalate_s=50)
    r = call.place_call(s)
    assert not r.get("ok")
    assert any(c["channel"] == "call" and "not placed" in c["detail"] for c in s["channel_log"])
