import json
import sys
import types

import pytest

from kaiku.contact import email as E
from kaiku.contact import ladder as L
from kaiku.contact import messages as M
from kaiku.contact import router as R

SUG = {"id": "sge1", "business_id": "SinceAI07", "business_name": "Furry Paw Vet Clinic", "holiday_date": "2026-12-24",
       "holiday_name_fi": "Jouluaatto", "holiday_name_en": "Christmas Eve", "kind": "hours",
       "proposed": [{"start": "09:00", "end": "13:00"}], "last_year_hours": [{"start": "09:00", "end": "13:00"}],
       "google_now": [{"start": "09:00", "end": "17:00"}], "channel_log": [],
       "decide_url": "https://kaiku.example/d/TOKEN123"}


@pytest.fixture(autouse=True)
def env(tmp_path, monkeypatch):
    monkeypatch.setenv("KAIKU_DATA_DIR", str(tmp_path))
    monkeypatch.setenv("KAIKU_ENV", str(tmp_path / "none.env"))
    for k in ("SMTP_HOST", "SMTP_USER", "SMTP_PASS", "SMTP_FROM", "OWNER_EMAIL", "WA_TOKEN", "OWNER_WHATSAPP"):
        monkeypatch.delenv(k, raising=False)
    L.cancel_pending()
    yield tmp_path
    L.cancel_pending()


def test_dry_run_writes_eml_with_link(env):
    r = E.send_decision_email(SUG, "owner@example.com")
    assert r["ok"] and r["dry_run"]
    eml = list((env / "email_outbox").glob("*_sge1.eml"))
    assert len(eml) == 1
    body = eml[0].read_text()
    assert "https://kaiku.example/d/TOKEN123" in body
    assert "Christmas Eve hours, one question" in body and "Furry Paw Vet Clinic" in body
    assert "text/html" in body and "text/plain" in body and "—" not in body
    log = json.loads((env / "email_log.jsonl").read_text().splitlines()[-1])
    assert log["to"] == "***@example.com" and "owner@" not in json.dumps(log)


def test_finnish_email(env):
    r = E.send_decision_email(dict(SUG, owner_language="fi"), "owner@example.com")
    assert "Jouluaaton aukioloajat, yksi kysymys" in r["subject"]


def test_real_smtp_path(env, monkeypatch):
    monkeypatch.delenv("KAIKU_NO_SMTP", raising=False)  # this test fakes smtplib itself
    monkeypatch.setenv("SMTP_HOST", "smtp.test")
    monkeypatch.setenv("SMTP_FROM", "kaiku@test.example")
    sent = []

    class FakeSMTP:
        def __init__(self, host, port, timeout=0): sent.append(("conn", host, port))
        def __enter__(self): return self
        def __exit__(self, *a): return False
        def ehlo(self): pass
        def starttls(self, context=None): sent.append("tls")
        def login(self, u, p): sent.append("login")
        def send_message(self, msg, from_addr=None, to_addrs=None): sent.append(("msg", msg["Subject"], to_addrs))

    monkeypatch.setattr(E.smtplib, "SMTP", FakeSMTP)
    r = E.send_decision_email(SUG, "owner@example.com")
    assert r == {"ok": True, "dry_run": False, "subject": "Furry Paw Vet Clinic: Christmas Eve hours, one question"}
    assert "tls" in sent and sent[0] == ("conn", "smtp.test", 587)


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
    FakeTimer.made = []
    monkeypatch.setattr(L, "_timer_factory", FakeTimer)
    monkeypatch.setenv("OWNER_EMAIL", "owner@example.com")
    monkeypatch.setenv("OWNER_WHATSAPP", "+358401234567")
    called = []
    mod = types.ModuleType("kaiku.contact.call")
    mod.place_call = lambda s: (called.append(s["id"]), {"ok": True, "conversation_id": "conv_fake"})[1]
    monkeypatch.setitem(sys.modules, "kaiku.contact.call", mod)
    import kaiku.contact as pkg
    monkeypatch.setattr(pkg, "call", mod, raising=False)
    monkeypatch.setattr(R, "is_decided", lambda sid: False)
    return called


def test_ladder_order_email_whatsapp_call(env, ladder):
    wa = FakeWA()
    s = dict(SUG, id="sgl1", channel_log=[])
    L.contact(s, client=wa, escalate_s=50, email_escalate_s=20)
    assert [c["channel"] for c in s["channel_log"]] == ["email"] and wa.sent == []
    t1 = FakeTimer.made[-1]
    assert t1.delay == 20
    t1.fire()
    assert wa.sent == ["text"] and [c["channel"] for c in s["channel_log"]] == ["email", "whatsapp", "whatsapp"]
    t2 = FakeTimer.made[-1]
    assert t2.delay == 50 and ladder == []
    t2.fire()
    assert ladder == ["sgl1"] and s["channel_log"][-1]["channel"] == "call"


def test_decision_cancels_pending(env, ladder, monkeypatch):
    wa = FakeWA()
    s = dict(SUG, id="sgl2", channel_log=[])
    L.contact(s, client=wa, escalate_s=50, email_escalate_s=20)
    t1 = FakeTimer.made[-1]
    monkeypatch.setattr(R, "is_decided", lambda sid: True)  # decided via web link
    assert t1.fire() == "decided" and wa.sent == []
    L.contact(dict(SUG, id="sgl3", channel_log=[]), client=wa, email_escalate_s=20)
    t = FakeTimer.made[-1]
    L.cancel_pending()
    assert t.cancelled
    L.contact(dict(SUG, id="sgl4", channel_log=[]), client=wa, email_escalate_s=20)
    t = FakeTimer.made[-1]
    L.cancel("sgl4")
    assert t.cancelled


def test_no_email_goes_straight_to_whatsapp(env, ladder, monkeypatch):
    monkeypatch.delenv("OWNER_EMAIL")
    wa = FakeWA()
    s = dict(SUG, id="sgl5", channel_log=[])
    L.contact(s, client=wa, escalate_s=50)
    assert wa.sent == ["text"] and s["channel_log"][0]["channel"] == "whatsapp"


def test_event_titles(env, ladder, monkeypatch):
    titles = []
    from kaiku import events
    monkeypatch.setattr(events, "emit", lambda e: titles.append(e.title_en))
    wa = FakeWA()
    s = dict(SUG, id="sgl6", channel_log=[])
    L.contact(s, client=wa, escalate_s=5, email_escalate_s=5)
    FakeTimer.made[-1].fire()
    FakeTimer.made[-1].fire()
    assert "Email drafted (dry run, no SMTP configured)" in titles
    assert "No reply by email, WhatsApp next" in titles
    assert "No reply on WhatsApp, Kaiku is calling" in titles


def test_standing_question_both_languages():
    en = M.standing_question_text(SUG)
    assert en == "Last year 9 to 13, this year 9 to 13 again. Want me to do this every Christmas Eve?"
    fi = M.standing_question_text(dict(SUG, owner_language="fi"))
    assert fi == "Viime vuonna 9-13, tänä vuonna taas 9-13. Tehdäänkö näin joka jouluaatto?"
    assert "—" not in en + fi
