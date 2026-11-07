import asyncio
import json

import pytest
from fastapi.testclient import TestClient

from kaiku import demo_contact as DC
from kaiku.app import app
from kaiku.contact import email as E
from kaiku.contact import ladder as L
from kaiku.contact import router as R

K = {"X-Kaiku-Key": "testkey"}


@pytest.fixture(autouse=True)
def env(tmp_path, monkeypatch):
    monkeypatch.setenv("KAIKU_DATA_DIR", str(tmp_path))
    monkeypatch.setenv("KAIKU_ENV", str(tmp_path / "none.env"))
    monkeypatch.setenv("KAIKU_ROOM_KEY", "testkey")
    monkeypatch.setenv("OWNER_EMAIL", "owner@own.example")
    monkeypatch.setenv("OWNER_WHATSAPP", "+358401111111")
    yield tmp_path


@pytest.fixture
def client():
    return TestClient(app)


def test_set_get_clear_masked(client, env):
    r = client.post("/api/demo/contact", headers=K, json={"email": "erik@fonecta.fi", "phone": "+358 45 123 4684"})
    assert r.status_code == 200 and r.json() == {"email": "e***@fonecta.fi", "phone": "+358***684", "set": True}
    assert "erik@" not in json.dumps(client.get("/api/demo/contact?key=testkey").json())
    assert json.loads((env / "demo_contact.json").read_text())["phone"] == "+358451234684"
    assert client.delete("/api/demo/contact", headers=K).json()["set"] is False
    client.post("/api/demo/contact", headers=K, json={"email": "a@b.fi"})
    assert client.post("/api/demo/contact", headers=K, json={"email": "", "phone": ""}).json()["set"] is False
    assert not (env / "demo_contact.json").exists()


def test_keyed(client):
    assert client.get("/api/demo/contact").status_code == 403
    assert client.post("/api/demo/contact", json={"email": "a@b.fi"}).status_code == 403
    assert client.delete("/api/demo/contact?key=wrong").status_code == 403


@pytest.mark.parametrize("body", [{"email": "nope"}, {"email": "a@b"}, {"phone": "0401234567"}, {"phone": "+12345"}, {"phone": "+1234567890123456"}])
def test_validation(client, body):
    r = client.post("/api/demo/contact", headers=K, json=body)
    assert r.status_code == 400 and r.json()["detail"]


def test_ladder_uses_override(env):
    s = {"id": "x1", "business_id": "furry-paw"}
    assert E.owner_email(s) == "owner@own.example" and L.owner_phone(s) == "358401111111"
    DC.save("erik@fonecta.fi", "+358451234684")
    assert E.owner_email(s) == "erik@fonecta.fi" and L.owner_phone(s) == "358451234684"
    DC.clear()
    assert E.owner_email(s) == "owner@own.example" and L.owner_phone(s) == "358401111111"


def test_whatsapp_step_sends_to_override(env):
    sent = []

    class Fake:
        def send_text(self, to, body, *a, **k):
            sent.append(to); return {"ok": True, "message_id": "m1"}
        send_buttons = lambda self, to, *a, **k: (sent.append(to), {"ok": True, "message_id": "m2"})[1]
        send_template = lambda self, to, *a, **k: (sent.append(to), {"ok": True, "message_id": "m3"})[1]
    DC.save("", "+358451234684")
    L.cancel_pending()
    L._whatsapp({"id": "x2", "business_id": "furry-paw", "kind": "no_change", "holiday_date": "2026-12-24"}, Fake(), 0)
    L.cancel_pending()
    assert sent and all(t == "358451234684" for t in sent)


def test_inbound_accepts_override_phone(env):
    assert R._is_owner_phone("+358401111111") and not R._is_owner_phone("+358451234684")
    DC.save("", "+358 45 123 4684")
    assert R._is_owner_phone("358451234684") and R._is_owner_phone("+358401111111")
    assert not R._is_owner_phone("+358400000000")


def test_call_default_number_is_override(env, monkeypatch):
    from kaiku.contact import call as C
    seen = {}

    class FakeApi:
        def call(self, method, path, payload):
            seen["to"] = payload["to_number"]; return 200, {"success": True, "conversation_id": "c1"}
    monkeypatch.setenv("ELEVENLABS_AGENT_ID", "a"); monkeypatch.setenv("ELEVENLABS_PHONE_NUMBER_ID", "p")
    DC.save("", "+358451234684")
    C.place_call({"id": "x3", "business_id": "furry-paw", "holiday_date": "2026-12-24"}, api=FakeApi())
    assert seen["to"] == "+358451234684"


def test_reset_keeps_override_unless_contact(client, env):
    DC.save("erik@fonecta.fi", "+358451234684")
    assert client.post("/api/reset?key=testkey").status_code == 200
    assert DC.email() == "erik@fonecta.fi"
    assert client.post("/api/reset?key=testkey&contact=1").status_code == 200
    assert DC.email() == "" and DC.phone() == ""
