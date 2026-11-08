import json

import pytest
from fastapi.testclient import TestClient

from kaiku import chain
from kaiku import demo_contact as DC
from kaiku.app import app
from kaiku.contact import ladder as L
from kaiku.tryit import router as T


@pytest.fixture(autouse=True)
def env(tmp_path, monkeypatch):
    monkeypatch.setenv("KAIKU_DATA_DIR", str(tmp_path))
    monkeypatch.setenv("KAIKU_ENV", str(tmp_path / "none.env"))
    monkeypatch.delenv("KAIKU_TRY_OFF", raising=False)
    monkeypatch.setenv("OWNER_WHATSAPP", "+358401111111")
    calls = []

    async def fake_reset(learn=0, contact=0):
        calls.append("reset"); return {}

    async def fake_run(business="furry-paw", date="2026-12-24"):
        calls.append("run"); return {"suggestion_id": "t1"}
    monkeypatch.setattr(chain, "reset_demo", fake_reset)
    monkeypatch.setattr(chain, "api_run", fake_run)
    from datetime import datetime
    monkeypatch.setattr(T, "_now", lambda: datetime(2026, 11, 8, 12, 0, tzinfo=T.HEL))
    return tmp_path


@pytest.fixture
def client():
    return TestClient(app)


def _unlock(env):
    (env / "try_lock.json").unlink(missing_ok=True)


def test_page(client):
    r = client.get("/try")
    assert r.status_code == 200 and "Three doors" in r.text and "Send me the proposal" in r.text
    assert 'href="/try"' in client.get("/").text


def test_email_door(client, env):
    r = client.post("/api/try", json={"door": "email", "email": "visitor@example.com"})
    assert r.status_code == 200
    j = r.json()
    assert j["suggestion_id"] == "t1" and j["contact"]["channels"] == ["email"] and j["contact"]["email"] == "v***@example.com"
    assert DC.masked()["channels"] == ["email"]
    log = (env / "try_log.jsonl").read_text()
    assert "visitor@example.com" not in log and "v***@example.com" in log and "visitor@example.com" not in r.text


def test_phone_door_rules(client, env):
    body = {"door": "phone", "email": "a@b.fi", "phone": "+358451234684", "own_number": False}
    assert client.post("/api/try", json=body).status_code == 400
    assert client.post("/api/try", json={**body, "own_number": True, "phone": "0401"}).status_code == 400
    assert client.post("/api/try", json={**body, "own_number": True, "email": "nope"}).status_code == 400
    r = client.post("/api/try", json={**body, "own_number": True})
    assert r.status_code == 200 and DC.masked()["channels"] == ["email", "whatsapp", "call"]
    assert "+358451234684" not in r.text


def test_phone_outside_hours(client, monkeypatch):
    from datetime import datetime
    monkeypatch.setattr(T, "_now", lambda: datetime(2026, 11, 8, 23, 0, tzinfo=T.HEL))
    r = client.post("/api/try", json={"door": "phone", "email": "a@b.fi", "phone": "+358451234684", "own_number": True})
    assert r.status_code == 400 and "between 8 and 22" in r.json()["detail"]
    assert client.post("/api/try", json={"door": "email", "email": "a@b.fi"}).status_code == 200


def test_same_phone_twice(client, env):
    body = {"door": "phone", "email": "a@b.fi", "phone": "+358451234684", "own_number": True}
    assert client.post("/api/try", json=body).status_code == 200
    _unlock(env)
    r = client.post("/api/try", json={**body, "email": "c@d.fi"})
    assert r.status_code == 429 and "opens again" in r.json()["detail"]


def test_email_cap_three(client, env):
    for _ in range(3):
        _unlock(env)
        assert client.post("/api/try", json={"door": "email", "email": "a@b.fi"}).status_code == 200
    _unlock(env)
    assert client.post("/api/try", json={"door": "email", "email": "a@b.fi"}).status_code == 429


def test_lock_held(client, env):
    assert client.post("/api/try", json={"door": "email", "email": "a@b.fi"}).status_code == 200
    r = client.post("/api/try", json={"door": "email", "email": "x@y.fi"})
    assert r.status_code == 409 and r.json()["seconds_left"] > 0 and "someone else" in r.json()["detail"]
    s = client.get("/api/try/status").json()
    assert s["busy"] and s["open_hours"] == "08-22 Helsinki"


def test_paused(client, env, monkeypatch):
    monkeypatch.setenv("KAIKU_TRY_OFF", "1")
    r = client.post("/api/try", json={"door": "email", "email": "a@b.fi"})
    assert r.status_code == 503 and "paused" in r.json()["detail"] and client.get("/api/try/status").json()["paused"]
    monkeypatch.delenv("KAIKU_TRY_OFF")
    (env / "try_off").write_text("")
    assert client.post("/api/try", json={"door": "email", "email": "a@b.fi"}).status_code == 503


def test_email_only_ladder_stops(env, monkeypatch):
    sent = []

    class Fake:
        def send_text(self, to, body, *a, **k):
            sent.append(to); return {"ok": True}
        send_buttons = send_template = lambda self, to, *a, **k: (sent.append(to), {"ok": True})[1]
    dialed = []
    from kaiku.contact import call as C
    monkeypatch.setattr(C, "place_call", lambda s, *a, **k: dialed.append(1) or {"ok": True})
    DC.save("v@example.com", "", channels=["email"])
    s = {"id": "tt1", "business_id": "furry-paw", "kind": "no_change", "holiday_date": "2026-12-24"}
    L.cancel_pending()
    L._whatsapp(s, Fake(), 0)
    assert not sent and "blocked" in s["channel_log"][-1]["detail"]
    assert L._call_step(s) == "blocked" and not dialed
    assert "blocked" in s["channel_log"][-1]["detail"]
    L.cancel_pending()
    DC.save("v@example.com", "+358451234684")  # all channels by default
    assert DC.allows("call") and DC.allows("whatsapp")


def test_fail_closed_after_clear_or_corrupt(env, monkeypatch):
    """The owner pressing 'Back to my own' (or a reset with contact=1) while an escalation is pending must not hand the
    pending WhatsApp or call to the owner's own phone; a corrupt contact file fails closed the same way."""
    sent = []

    class Fake:
        def send_text(self, to, body, *a, **k):
            sent.append(to); return {"ok": True}
        send_buttons = send_template = lambda self, to, *a, **k: (sent.append(to), {"ok": True})[1]
    dialed = []
    from kaiku.contact import call as C
    monkeypatch.setattr(C, "place_call", lambda s, *a, **k: dialed.append(1) or {"ok": True})
    DC.save("v@example.com", "", channels=["email"])
    DC.set_mode(["email"], 600)
    DC.clear()
    s = {"id": "tt2", "business_id": "furry-paw", "kind": "no_change", "holiday_date": "2026-12-24"}
    L._whatsapp(s, Fake(), 0)
    assert not sent and "blocked" in s["channel_log"][-1]["detail"]
    assert L._call_step(s) == "blocked" and not dialed
    DC.clear_mode()
    (env / "demo_contact.json").write_text("{not json")
    assert DC.allows("whatsapp") is False and DC.allows("call") is False and DC.allows("email") is True
    (env / "demo_contact.json").unlink()
    assert DC.allows("whatsapp") and DC.allows("call")
    L.cancel_pending()


def test_try_sets_the_fail_closed_marker(client, env):
    _unlock(env)
    r = client.post("/api/try", json={"door": "email", "email": "m@example.org"})
    assert r.status_code == 200
    assert json.loads((env / "try_mode.json").read_text())["channels"] == ["email"]
    DC.clear()
    assert DC.allows("call") is False and DC.allows("whatsapp") is False
    DC.clear_mode()


def test_long_input_rejected_before_any_run(client, env):
    _unlock(env)
    r = client.post("/api/try", json={"door": "email", "email": "a" * 300 + "@b.fi"})
    assert r.status_code == 400
    r = client.post("/api/try", json={"door": "email", "email": "a" * 20000 + "@b.fi"})
    assert r.status_code == 413
    assert not (env / "try_lock.json").exists()
