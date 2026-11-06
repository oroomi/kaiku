import asyncio
import json
import os

import pytest
from fastapi import FastAPI
from fastapi.testclient import TestClient

from kaiku.contact import ladder as L
from kaiku.contact import messages as M
from kaiku.contact import router as R
from kaiku.contact import whatsapp as W

SUG = {"id": "sg1", "business_id": "SinceAI07", "business_name": "Furry Paw Vet Clinic", "holiday_date": "2026-12-24",
       "holiday_name_fi": "Jouluaatto", "holiday_name_en": "Christmas Eve", "kind": "hours",
       "proposed": [{"start": "09:00", "end": "13:00"}], "last_year_hours": [{"start": "09:00", "end": "13:00"}],
       "google_now": [{"start": "09:00", "end": "17:00"}], "channel_log": []}
SUG_FI = dict(SUG, owner_language="fi")
PHONE = "358401234567"


@pytest.fixture(autouse=True)
def isolated(tmp_path, monkeypatch):
    monkeypatch.setenv("KAIKU_DATA_DIR", str(tmp_path))
    monkeypatch.setenv("WA_VERIFY_TOKEN", "vt-test")
    monkeypatch.setenv("OWNER_WHATSAPP", "+358 40 123 4567")
    monkeypatch.delenv("WA_APP_SECRET", raising=False)
    W.set_client(None)
    yield
    L.cancel_pending()
    W.set_client(None)


class Fake:
    """Records calls; returns scripted responses."""
    def __init__(self, responses=None):
        self.calls = []
        self.responses = list(responses or [])

    def __call__(self, method, url, headers, payload):
        self.calls.append((method, url, headers, payload))
        if self.responses:
            return self.responses.pop(0)
        return 200, {"messages": [{"id": f"wamid.{len(self.calls)}"}]}


def client(fake):
    return W.WhatsAppClient(token="TOK", phone_id="123", transport=fake)


# ---------------------------------------------------------------- messages

ENGINE = {**SUG_FI, "message_fi": "Hei Furry Paw Vet Clinic! Jouluaatto on torstaina 24.12. Viime vuonna olitte auki 9-13. Ehdotus: to 24.12. klo 9-13.",
          "message_en": "Hi Furry Paw Vet Clinic! Christmas Eve is on Thursday 24.12. Last year you were open 09:00-13:00. We suggest: Thu 24.12. 09:00-13:00.",
          "decide_url": None}


def test_suggestion_snapshot_fallback():
    assert M.suggestion_text(SUG_FI) == (
        "Hei, Furry Paw Vet Clinic!\n\n"
        "Jouluaatto on torstaina 24.12.\n"
        "Viime vuonna aukioloaikanne tuona päivänä oli 9-13.\n"
        "Googlessa näkyy nyt 9-17, mikä ei vastaa ehdotustamme, joten asiakas voi saapua suljetun oven eteen.\n\n"
        "Ehdotamme, että jouluaattona (24.12.) aukioloaikanne on 9-13.\n"
        "Voitte hyväksyä yhdellä napautuksella, muokata aikaa tai jättää ehdotuksen väliin. Päätös on aina teidän.")


def test_engine_message_used_verbatim_and_url_line():
    t = M.suggestion_text(ENGINE)
    assert t.startswith(ENGINE["message_fi"]) and "Pyhäpäivä" not in t and "sinun" not in t
    assert "Voitte myös päättää" not in t
    u = M.suggestion_text(dict(ENGINE, decide_url="https://x.example/d/1"))
    assert u.endswith("Voitte myös päättää selaimessa: https://x.example/d/1")
    assert M.suggestion_text_en(dict(ENGINE, decide_url="https://x.example/d/1")).endswith(
        "You can also decide in the browser: https://x.example/d/1")
    ask = dict(ENGINE, kind="ask", decide_url="https://x.example/d/1")
    assert "https://x.example/d/1" in M.ask_text(ask) and "https://x.example/d/1" in M.ask_text_en(ask)


def test_fallback_never_claims_missing_facts():
    bare = {"id": "s", "kind": "hours", "holiday_date": "2026-12-24", "proposed": [{"start": "09:00", "end": "13:00"}]}
    t = M.suggestion_text(dict(bare, owner_language="fi"))
    assert "Viime vuonna" not in t and "Googlessa" not in t and "Hakukoneissa" not in t and "Pyhäpäivä" not in t
    assert "24.12." in t
    assert "Viime vuonna" not in M.suggestion_text(dict(SUG_FI, last_year_hours=None))


def test_register_is_polite_plural():
    ask = dict(SUG_FI, kind="ask", proposed=None)
    closed = dict(SUG_FI, kind="closed", proposed=None)
    for t in (M.suggestion_text(SUG_FI), M.suggestion_text(closed), M.ask_text(ask), M.edit_prompt_text("fi"),
              M.decline_thanks_text("fi"), M.unknown_reply_text("fi")):
        for bad in (" sinun", " sinä", "Voit ", "olet ", "Kirjoita ", "Kerro "):
            assert bad not in t, (bad, t)


def test_receipt_snapshot():
    r = {"holiday_name_fi": "Jouluaatto", "hours": [{"start": "09:00", "end": "13:00"}],
         "publishers": ["Google", "Apple Maps"]}
    assert M.receipt_text(dict(r, owner_language="fi")) == ("Kiitos! Jouluaaton aukioloajat 9-13 on nyt tallennettu. "
                                 "Ne näkyvät Googlessa, Apple Mapsissa ja Fonectan palveluissa.")
    c = M.receipt_text({"holiday_name_fi": "Joulupäivä", "hours": "closed", "publishers": ["Google"], "owner_language": "fi"})
    assert "Se näkyy" in c and "Ne näkyvät" not in c


def test_other_messages_and_no_em_dash():
    ask = dict(SUG_FI, kind="ask", proposed=None)
    nc = dict(SUG_FI, kind="no_change")
    closed = dict(SUG_FI, kind="closed", proposed=None)
    assert "esimerkiksi \"9-13\"" in M.ask_text(ask)
    assert "Mitään ei tarvitse tehdä" in M.no_change_text(nc)
    assert "olette suljettuna." in M.suggestion_text(closed) and "olette suljettu." not in M.suggestion_text(closed)
    for t in (M.edit_prompt_text("fi"), M.decline_thanks_text("fi"), M.unknown_reply_text("fi"), M.suggestion_text_en(SUG),
              M.ask_text_en(ask), M.no_change_text_en(nc), M.receipt_text_en({"hours": "closed"})):
        assert "\u2014" not in t and "\u2013" not in t
    assert M.essive("Loppiainen") == "loppiaisena" and M.essive("Isänpäivä") == "isänpäivänä"
    assert M.fi_hours([{"start": "09:30", "end": "18:00"}]) == "9.30-18"


def test_final_messages_export(tmp_path):
    md = M.all_final_messages(tmp_path / "f.md")
    assert (tmp_path / "f.md").exists() and "Kiitos! Jouluaaton aukioloajat 9-13" in md and "Done. Christmas Eve" in md and "olette suljettu." not in md and "Pyhäpäivä" not in md and "\u2014" not in md


# ---------------------------------------------------------------- English (the default)

def test_owner_lang_default_and_fi():
    assert M.owner_lang(None) == "en" and M.owner_lang({}) == "en" and M.owner_lang(SUG) == "en"
    assert M.owner_lang({"owner_language": "fi"}) == "fi" and M.owner_lang({"business": {"owner_language": "fi"}}) == "fi"
    assert M.owner_lang({"owner_language": "xx"}) == "en"


def test_english_messages_default():
    t = M.suggestion_text(SUG)
    assert t.startswith("Hi, Furry Paw Vet Clinic!") and "Christmas Eve falls on Thursday 24.12." in t
    assert "your hours are 9 to 13" in t or "9 to 13" in t
    ask = dict(SUG, kind="ask", proposed=None)
    assert "Reply to this message" in M.ask_text(ask) and "9-13" in M.ask_text(ask)
    assert "regular hours apply" in M.no_change_text(dict(SUG, kind="no_change"))
    assert M.edit_prompt_text() == "Reply with the new hours, like 9-13, or 'closed'."
    assert M.receipt_text({"holiday_name_en": "Christmas Eve", "holiday_date": "2026-12-24", "hours": [{"start": "09:00", "end": "13:00"}]}) == (
        "Done. Christmas Eve 24.12. hours 9-13 are saved and will show on Google, Fonecta Finder, 020202 and the other channels Connect publishes to.")
    assert M.receipt_text({"holiday_name_en": "Christmas Day", "hours": "closed"}).startswith("Done. Christmas Day closure is saved")
    for fn in (M.decline_thanks_text, M.unknown_reply_text, M.unknown_suggestion_text):
        out = fn()
        assert "ä" not in out and "\u2014" not in out
    assert M.button_titles(SUG) == [("approve", "Approve"), ("edit", "Edit"), ("decline", "No thanks")]
    assert M.button_titles(SUG_FI)[0] == ("approve", "Hyväksy")


@pytest.mark.parametrize("text,expected", [
    ("yes", {"action": "approve"}), ("Approve", {"action": "approve"}), ("ok", {"action": "approve"}),
    ("Sure!", {"action": "approve"}), ("yeah", {"action": "approve"}),
    ("no", {"action": "decline"}), ("No thanks", {"action": "decline"}), ("decline", {"action": "decline"}),
    ("closed", {"action": "edit", "edited": "closed"}), ("We're closed", {"action": "edit", "edited": "closed"}),
    ("9-13", {"action": "edit", "edited": [{"start": "09:00", "end": "13:00"}]}),
    ("9am-1pm", {"action": "edit", "edited": [{"start": "09:00", "end": "13:00"}]}),
    ("9 am - 1 pm", {"action": "edit", "edited": [{"start": "09:00", "end": "13:00"}]}),
    ("10:30 to 14", {"action": "edit", "edited": [{"start": "10:30", "end": "14:00"}]}),
    ("nine to one", {"action": "edit", "edited": [{"start": "09:00", "end": "13:00"}]}),
    ("13-9", None), ("maybe later", None),
])
def test_free_text_english(text, expected):
    assert R.parse_free_text(text) == expected


def test_english_webhook_flow_replies_in_english():
    f = Fake()
    R.register_sent(PHONE, "sg1", "wamid.CTX", None, "en")
    run(R.handle_payload(button_payload("edit"), client(f)))
    r = run(R.handle_payload(text_payload("sorry what"), client(f)))
    assert r["decisions"] == [] and any("Sorry, I did not understand" in str(c[3]) for c in f.calls)
    r = run(R.handle_payload(text_payload("9am-1pm", mid="wamid.IN9"), client(f)))
    assert r["decisions"][0]["edited"] == [{"start": "09:00", "end": "13:00"}]


def test_finnish_owner_still_gets_finnish_replies():
    f = Fake()
    R.register_sent(PHONE, "sg1", "wamid.CTX", None, "fi")
    run(R.handle_payload(button_payload("edit"), client(f)))
    assert any("Kirjoittakaa uusi aukioloaika" in str(c[3]) for c in f.calls)


# ---------------------------------------------------------------- payloads and errors

def test_button_payload():
    p = W.WhatsAppClient.buttons_payload("+358 40 123 4567", "body")
    assert p["to"] == "358401234567" and p["type"] == "interactive"
    btns = p["interactive"]["action"]["buttons"]
    assert [b["reply"]["title"] for b in btns] == ["Approve", "Edit", "No thanks"]
    assert [t for _, t in W.FI_BUTTONS] == ["Hyväksy", "Muokkaa", "Ei kiitos"]
    assert all(len(b["reply"]["title"]) <= 20 for b in btns)
    with pytest.raises(ValueError):
        W.WhatsAppClient.buttons_payload(PHONE, "b", [("a", "x")] * 4)
    with pytest.raises(ValueError):
        W.WhatsAppClient.buttons_payload(PHONE, "b", [("a", "x" * 21)])


def test_send_and_url_and_log(tmp_path):
    f = Fake()
    c = W.WhatsAppClient(token="SECRETTOK", phone_id="999", transport=f, log_path=tmp_path / "log.jsonl")
    r = c.send_text(PHONE, "moi")
    assert r == {"ok": True, "message_id": "wamid.1", "status": 200}
    assert f.calls[0][1] == "https://graph.facebook.com/v21.0/999/messages"
    assert f.calls[0][2]["Authorization"] == "Bearer SECRETTOK"
    log = (tmp_path / "log.jsonl").read_text()
    assert "SECRETTOK" not in log and "moi" in log
    c.send_template(PHONE)
    assert f.calls[1][3]["template"] == {"name": "hello_world", "language": {"code": "en_US"}}
    c.mark_read("wamid.X")
    assert f.calls[2][3] == {"messaging_product": "whatsapp", "status": "read", "message_id": "wamid.X"}


def test_error_mapping():
    e1 = (400, {"error": {"code": 131047, "message": "Re-engagement message"}})
    e2 = (400, {"error": {"code": 131030, "message": "Recipient phone number not in allowed list"}})
    c = client(Fake([e1, e2]))
    r1 = c.send_text(PHONE, "x")
    assert r1["needs_template"] is True and not r1["ok"]
    r2 = c.send_text(PHONE, "x")
    assert "allowed list" in r2["error"] and "needs_template" not in r2


def test_unconfigured_is_blocked_not_crash():
    c = W.WhatsAppClient(token="", phone_id="", transport=Fake())
    assert c.send_text(PHONE, "x")["blocked"] is True


# ---------------------------------------------------------------- free text

@pytest.mark.parametrize("text,expected", [
    ("9-13", {"action": "edit", "edited": [{"start": "09:00", "end": "13:00"}]}),
    ("9:00-13:00", {"action": "edit", "edited": [{"start": "09:00", "end": "13:00"}]}),
    ("klo 10-15", {"action": "edit", "edited": [{"start": "10:00", "end": "15:00"}]}),
    ("10.30 - 15", {"action": "edit", "edited": [{"start": "10:30", "end": "15:00"}]}),
    ("Suljettu", {"action": "edit", "edited": "closed"}),
    ("kiinni!", {"action": "edit", "edited": "closed"}),
    ("ei", {"action": "decline"}),
    ("Ei kiitos", {"action": "decline"}),
    ("ok", {"action": "approve"}), ("Kyllä", {"action": "approve"}), ("jees", {"action": "approve"}),
    ("13-9", None), ("moi", None), ("", None), ("25-26", None),
])
def test_free_text(text, expected):
    assert R.parse_free_text(text) == expected


# ---------------------------------------------------------------- webhook parsing (Meta documented shapes)

def wrap(value):
    return {"object": "whatsapp_business_account",
            "entry": [{"id": "WABA", "changes": [{"field": "messages", "value": {
                "messaging_product": "whatsapp", "metadata": {"display_phone_number": "15551234567", "phone_number_id": "123"}, **value}}]}]}


def button_payload(bid="approve", ctx="wamid.CTX", mid="wamid.IN1"):
    return wrap({"contacts": [{"profile": {"name": "Dayo"}, "wa_id": PHONE}],
                 "messages": [{"context": {"from": "15551234567", "id": ctx}, "from": PHONE, "id": mid, "timestamp": "1700000000",
                               "type": "interactive", "interactive": {"type": "button_reply", "button_reply": {"id": bid, "title": "Hyväksy"}}}]})


def text_payload(body, mid="wamid.IN2"):
    return wrap({"messages": [{"from": PHONE, "id": mid, "timestamp": "1700000001", "type": "text", "text": {"body": body}}]})


STATUS = wrap({"statuses": [{"id": "wamid.OUT", "status": "delivered", "timestamp": "1700000002", "recipient_id": PHONE}]})


def run(coro):
    return asyncio.run(coro)


def test_parse_inbound_shapes():
    assert R.parse_inbound(button_payload())[0]["button_id"] == "approve"
    assert R.parse_inbound(text_payload("9-13"))[0]["text"] == "9-13"
    st = R.parse_inbound(STATUS)[0]
    assert st["kind"] == "status" and st["status"] == "delivered"


def test_button_approve_uses_context_message_map():
    R.register_sent(PHONE, "sg1", "wamid.CTX", "SinceAI07")
    res = run(R.handle_payload(button_payload("approve"), client(Fake())))
    d = res["decisions"][0]
    assert d["suggestion_id"] == "sg1" and d["action"] == "approve" and d["via"] == "whatsapp" and d["edited"] is None
    assert R.is_decided("sg1")
    # redelivery of the same webhook is ignored
    assert run(R.handle_payload(button_payload("approve"), client(Fake())))["decisions"] == []


def test_button_id_carries_suggestion_id():
    R.register_sent(PHONE, "other", "wamid.Z")
    R.register_sent("358409999999", "sg9", "wamid.Y")
    res = run(R.handle_payload(button_payload("decline:sg9", ctx="wamid.unknown"), client(Fake())))
    assert res["decisions"][0]["suggestion_id"] == "sg9" and res["decisions"][0]["action"] == "decline"


def test_button_unknown_suggestion_replies_no_decision(monkeypatch):
    got = []
    import types, sys
    mod = types.ModuleType("kaiku.chain"); mod.on_decision = lambda d: got.append(d)
    monkeypatch.setitem(sys.modules, "kaiku.chain", mod)
    import kaiku; monkeypatch.setattr(kaiku, "chain", mod, raising=False)
    R.register_sent(PHONE, "sg1", "wamid.CTX")
    f = Fake()
    res = run(R.handle_payload(button_payload("approve:nonexistent"), client(f)))
    assert res["decisions"] == [] and got == [] and res["unknown"] == ["nonexistent"]
    assert any("I could not find the suggestion this reply belongs to." in str(c[3]) for c in f.calls)
    assert not R.is_decided("nonexistent")


def test_edit_flow_then_free_text():
    f = Fake()
    R.register_sent(PHONE, "sg1", "wamid.CTX")
    r1 = run(R.handle_payload(button_payload("edit"), client(f)))
    assert r1["decisions"] == [] and r1["edit_requested"] == ["sg1"]
    assert any("Reply with the new hours, like 9-13, or 'closed'." in str(c[3]) for c in f.calls)
    r2 = run(R.handle_payload(text_payload("klo 10-15"), client(f)))
    assert r2["decisions"][0]["action"] == "edit" and r2["decisions"][0]["edited"] == [{"start": "10:00", "end": "15:00"}]


def test_edit_flow_garbage_reprompts():
    f = Fake()
    R.register_sent(PHONE, "sg1", "wamid.CTX")
    run(R.handle_payload(button_payload("edit"), client(f)))
    r = run(R.handle_payload(text_payload("en tiedä"), client(f)))
    assert r["decisions"] == [] and r["replies"] == 1


def test_text_closed_and_decline_sends_thanks():
    f = Fake()
    R.register_sent(PHONE, "sg1", "wamid.CTX")
    r = run(R.handle_payload(text_payload("suljettu"), client(f)))
    assert r["decisions"][0]["edited"] == "closed"
    R.register_sent(PHONE, "sg2", "wamid.C2")
    r = run(R.handle_payload(text_payload("ei", mid="wamid.IN3"), client(f)))
    assert r["decisions"][0]["action"] == "decline"
    assert any("Thanks for replying" in str(c[3]) for c in f.calls)


def test_status_callback_no_decision():
    r = run(R.handle_payload(STATUS, client(Fake())))
    assert r["decisions"] == [] and r["statuses"][0]["status"] == "delivered"


def test_forwards_to_chain(monkeypatch):
    import sys, types
    got = []
    chain = types.ModuleType("kaiku.chain"); chain.on_decision = lambda d: got.append(d)
    import kaiku
    monkeypatch.setitem(sys.modules, "kaiku.chain", chain); monkeypatch.setattr(kaiku, "chain", chain, raising=False)
    R.register_sent(PHONE, "sg1", "wamid.CTX")
    run(R.handle_payload(button_payload("approve"), client(Fake())))
    assert got and got[0]["action"] == "approve"


# ---------------------------------------------------------------- HTTP

def make_app():
    app = FastAPI(); app.include_router(R.router); return TestClient(app)


def test_verify_handshake():
    c = make_app()
    ok = c.get("/webhooks/whatsapp", params={"hub.mode": "subscribe", "hub.verify_token": "vt-test", "hub.challenge": "12345"})
    assert ok.status_code == 200 and ok.text == "12345"
    assert c.get("/webhooks/whatsapp", params={"hub.mode": "subscribe", "hub.verify_token": "bad", "hub.challenge": "1"}).status_code == 403


def test_post_webhook_and_signature(monkeypatch):
    import hashlib, hmac
    R.register_sent(PHONE, "sg1", "wamid.CTX")
    monkeypatch.setattr(W, "get_client", lambda: client(Fake()))
    c = make_app()
    body = json.dumps(button_payload("approve")).encode()
    assert c.post("/webhooks/whatsapp", content=body).json()["decisions"] == 1
    monkeypatch.setenv("WA_APP_SECRET", "s3")
    assert c.post("/webhooks/whatsapp", content=body).status_code == 403
    sig = "sha256=" + hmac.new(b"s3", body, hashlib.sha256).hexdigest()
    assert c.post("/webhooks/whatsapp", content=body, headers={"x-hub-signature-256": sig}).status_code == 200


# ---------------------------------------------------------------- ladder

def test_ladder_sends_buttons_to_owner_and_logs():
    f = Fake()
    s = dict(SUG, channel_log=[])
    L.contact(s, client=client(f), escalate_s=10**6)
    assert s["status"] == "sent" and s["channel_log"][0]["channel"] == "whatsapp"
    p = f.calls[0][3]
    assert p["to"] == "358401234567" and p["interactive"]["action"]["buttons"][0]["reply"]["id"] == "approve:sg1"
    # reply maps back via wamid.1
    res = run(R.handle_payload(button_payload("approve:sg1", ctx="wamid.1"), client(Fake())))
    assert res["decisions"][0]["suggestion_id"] == "sg1"


def test_ladder_template_first_when_outside_window():
    f = Fake([(400, {"error": {"code": 131047, "message": "x"}}), (200, {"messages": [{"id": "wamid.T"}]}),
              (200, {"messages": [{"id": "wamid.B"}]}), (200, {})])
    s = dict(SUG, channel_log=[])
    L.contact(s, client=client(f), escalate_s=10**6)
    assert f.calls[1][3]["type"] == "template"
    assert "template first" in s["channel_log"][0]["detail"]
    # owner replies "hei" to the template -> the real buttons arrive
    run(R.handle_payload(text_payload("hei", mid="wamid.IN9"), client(f)))
    assert any(c[3].get("type") == "interactive" for c in f.calls[2:])


def test_ladder_escalates_to_call_when_undecided(monkeypatch):
    import sys, types, time
    called = []
    mod = types.ModuleType("kaiku.contact.call"); mod.place_call = lambda s: called.append(s["id"])
    monkeypatch.setitem(sys.modules, "kaiku.contact.call", mod)
    import kaiku.contact as pkg
    monkeypatch.setattr(pkg, "call", mod, raising=False)
    s = dict(SUG, id="sgcall", channel_log=[])
    L.contact(s, client=client(Fake()), escalate_s=0.05)
    time.sleep(0.4)
    assert called == ["sgcall"] and s["channel_log"][-1]["channel"] == "call"


def test_ladder_no_call_when_decided():
    s = dict(SUG, id="sgdone", channel_log=[])
    L.contact(s, client=client(Fake()), escalate_s=10**6)
    R.register_sent(PHONE, "sgdone", "wamid.1")
    run(R.handle_payload(button_payload("approve", ctx="wamid.1", mid="wamid.IN7"), client(Fake())))
    assert L._call_step(s) == "decided"


def test_call_lane_missing_is_logged():
    s = dict(SUG, id="sgx", channel_log=[])
    assert L._call_step(s) in ("not_configured", "placed", "failed")


# ---------------------------------------------------------------- template path (WA_TEMPLATE_NAME)

def test_template_hours_payload_shape():
    f = Fake([(200, {"messages": [{"id": "wamid.T"}]})])
    r = client(f).send_template_hours("+358 40 123 4567", "Furry Paw Vet Clinic", "24.12.", "9-13", "jouluaatto", "sg1")
    assert r["ok"]
    assert f.calls[0][3] == {
        "messaging_product": "whatsapp", "to": "358401234567", "type": "template",
        "template": {"name": "kaiku_hours_fi", "language": {"code": "fi"}, "components": [
            {"type": "body", "parameters": [{"type": "text", "text": t} for t in
                                            ("Furry Paw Vet Clinic", "24.12.", "9-13", "jouluaatto")]},
            {"type": "button", "sub_type": "quick_reply", "index": "0", "parameters": [{"type": "payload", "payload": "approve:sg1"}]},
            {"type": "button", "sub_type": "quick_reply", "index": "1", "parameters": [{"type": "payload", "payload": "edit:sg1"}]},
            {"type": "button", "sub_type": "quick_reply", "index": "2", "parameters": [{"type": "payload", "payload": "decline:sg1"}]}]}}


def test_ladder_template_switch(monkeypatch):
    monkeypatch.setenv("KAIKU_ENV", "/nonexistent/.env")
    monkeypatch.setenv("WA_TEMPLATE_NAME", "kaiku_hours_fi")
    f = Fake([(200, {"messages": [{"id": "wamid.T"}]})])
    s = L.contact(dict(SUG_FI, id="sgt", channel_log=[]), client=client(f), escalate_s=10**6)
    p = f.calls[0][3]
    assert p["type"] == "template" and p["template"]["name"] == "kaiku_hours_fi"
    assert p["template"]["components"][0]["parameters"][1]["text"] == "24.12."
    assert p["template"]["components"][1]["parameters"][0]["payload"] == "approve:sgt"
    assert s["status"] == "sent" and len(f.calls) == 1


def test_ladder_english_ignores_finnish_template(monkeypatch):
    monkeypatch.setenv("KAIKU_ENV", "/nonexistent/.env")
    monkeypatch.setenv("WA_TEMPLATE_NAME", "kaiku_hours_fi")
    monkeypatch.delenv("WA_TEMPLATE_NAME_EN", raising=False)
    f = Fake([(200, {"messages": [{"id": "wamid.E"}]})])
    L.contact(dict(SUG, id="sge", channel_log=[]), client=client(f), escalate_s=10**6)
    p = f.calls[0][3]
    assert p["type"] == "interactive"
    assert [b["reply"]["title"] for b in p["interactive"]["action"]["buttons"]] == ["Approve", "Edit", "No thanks"]
    assert [b["reply"]["id"] for b in p["interactive"]["action"]["buttons"]] == ["approve:sge", "edit:sge", "decline:sge"]
    assert p["interactive"]["body"]["text"].startswith("Hi, Furry Paw Vet Clinic!")
    monkeypatch.setenv("WA_TEMPLATE_NAME_EN", "kaiku_hours_en")
    f2 = Fake([(200, {"messages": [{"id": "wamid.E2"}]})])
    L.contact(dict(SUG, id="sge2", channel_log=[], reasons=[{"text_en": "Last Christmas Eve you were open 9-13."}]), client=client(f2), escalate_s=10**6)
    tp = f2.calls[0][3]["template"]
    assert tp["name"] == "kaiku_hours_en" and tp["language"]["code"] == "en"
    assert [x["text"] for x in tp["components"][0]["parameters"]] == [
        "Furry Paw Vet Clinic", "24.12.", "9-13", "Last Christmas Eve you were open 9-13"]


def test_ladder_default_stays_interactive(monkeypatch):
    monkeypatch.setenv("KAIKU_ENV", "/nonexistent/.env")
    monkeypatch.delenv("WA_TEMPLATE_NAME", raising=False)
    f = Fake([(200, {"messages": [{"id": "wamid.B"}]})])
    L.contact(dict(SUG, id="sgb", channel_log=[]), client=client(f), escalate_s=10**6)
    assert f.calls[0][3]["type"] == "interactive"


# ---------------------------------------------------------------- live (only with KAIKU_LIVE=1)

def _live_env() -> dict:
    """Read the real values straight from .env (python-dotenv unquotes WA_TOKEN="..."). os.environ is NOT used for
    OWNER_WHATSAPP: other test modules overwrite it with a fake number at import time."""
    try:
        from dotenv import dotenv_values
        vals = dotenv_values(W.env_path())
    except ImportError:
        vals = {}
    return {k: vals.get(k) for k in ("WA_TOKEN", "WA_PHONE_ID", "OWNER_WHATSAPP")}


@pytest.mark.live
@pytest.mark.skipif(os.environ.get("KAIKU_LIVE") != "1", reason="sends a real WhatsApp message, set KAIKU_LIVE=1")
def test_live_send_buttons_to_owner():
    live = _live_env()
    if not all(live.values()):
        pytest.skip("no WA_TOKEN in .env")
    c = W.WhatsAppClient(token=live["WA_TOKEN"], phone_id=live["WA_PHONE_ID"])
    r = c.send_buttons(live["OWNER_WHATSAPP"], "Kaiku testi: painaa jotakin painiketta.")
    assert r["ok"] or r.get("needs_template"), r
