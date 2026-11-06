import asyncio
import json

import pytest

from kaiku.contact import call as C
from kaiku.contact import call_router as CR
from kaiku.contact import router as R

SUG = {"id": "sg-1", "business_id": "SinceAI07", "business_name": "Furry Paw Vet Clinic", "holiday_date": "2026-12-24",
       "holiday_name_fi": "Jouluaatto", "kind": "hours", "proposed": [{"start": "09:00", "end": "13:00"}],
       "last_year_hours": [{"start": "09:00", "end": "13:00"}],
       "reasons": [{"source": "last_year", "dataset_id": "x", "text_fi": "Viime jouluaattona olitte auki 9-13.", "text_en": "."}]}


class Fake:
    def __init__(self, replies):
        self.replies, self.calls = list(replies), []

    def __call__(self, method, url, headers, payload):
        self.calls.append((method, url, headers, payload))
        return self.replies.pop(0)


@pytest.fixture(autouse=True)
def env(tmp_path, monkeypatch):
    p = tmp_path / ".env"
    p.write_text("ELEVENLABS_VOICE_ID=voice1\nPUBLIC_URL=https://x.example\n")
    monkeypatch.setenv("KAIKU_ENV", str(p))
    monkeypatch.setenv("KAIKU_DATA_DIR", str(tmp_path))
    for k in ("ELEVENLABS_AGENT_ID", "ELEVENLABS_PHONE_NUMBER_ID", "ELEVENLABS_WEBHOOK_ID", "ELEVENLABS_WEBHOOK_SECRET"):
        monkeypatch.delenv(k, raising=False)
    monkeypatch.setenv("ELEVENLABS_VOICE_ID", "voice1")
    monkeypatch.setenv("PUBLIC_URL", "https://x.example")
    monkeypatch.setenv("OWNER_WHATSAPP", "+358451291684")
    return p


def test_agent_payload_shape_and_env_store(env):
    f = Fake([(200, {"agent_id": "ag_1"})])
    r = C.ensure_agent(C.Api("k", f))
    assert r == {"ok": True, "agent_id": "ag_1", "created": True}
    m, url, h, p = f.calls[0]
    assert url.endswith("/v1/convai/agents/create") and h["xi-api-key"] == "k"
    cc = p["conversation_config"]
    assert cc["agent"]["language"] == "fi" and cc["tts"]["voice_id"] == "voice1"
    assert cc["tts"]["model_id"] == "eleven_flash_v2_5" and "Hyväksytkö" in cc["agent"]["prompt"]["prompt"]
    assert "{{holiday_date_fi}}" in cc["agent"]["prompt"]["prompt"]
    assert "—" not in json.dumps(p, ensure_ascii=False) and "–" not in json.dumps(p, ensure_ascii=False)
    assert "ELEVENLABS_AGENT_ID=ag_1" in env.read_text()
    assert oct(env.stat().st_mode)[-3:] == "600"
    assert C.ensure_agent(C.Api("k", Fake([])))["created"] is False  # idempotent, no call


def test_webhook_stores_secret(env):
    f = Fake([(200, {"webhook_id": "wh1", "webhook_secret": "s3"}), (200, {})])
    assert C.ensure_webhook(C.Api("k", f))["ok"]
    assert f.calls[0][3]["settings"]["webhook_url"] == "https://x.example/webhooks/call"
    assert "ELEVENLABS_WEBHOOK_SECRET=s3" in env.read_text()


def test_number_reuse_existing(env):
    f = Fake([(200, {"phone_numbers": [{"phone_number_id": "ph1"}]})])
    assert C.ensure_phone_number(C.Api("k", f))["phone_number_id"] == "ph1"


def test_number_price_guard(env):
    f = Fake([(200, {"phone_numbers": []}), (200, {"phone_numbers": [{"phone_number": "+1555", "monthly_price": 25}]})])
    r = C.ensure_phone_number(C.Api("k", f))
    assert not r["ok"] and "25" in r["reason"]
    assert all(c[0] == "GET" for c in f.calls)  # nothing purchased


def test_number_unknown_price_not_bought(env):
    f = Fake([(200, []), (200, [{"phone_number": "+1555"}])])
    assert not C.ensure_phone_number(C.Api("k", f))["ok"]
    assert len(f.calls) == 2


def test_number_purchase_when_cheap(monkeypatch, env):
    monkeypatch.setenv("KAIKU_ALLOW_NUMBER_PURCHASE", "1")
    f = Fake([(200, []), (200, [{"phone_number": "+1555", "monthly_price": 1.0}, {"phone_number": "+1666", "monthly_price": 0}]),
              (200, {"phone_number_id": "ph9"})])
    r = C.ensure_phone_number(C.Api("k", f))
    assert r["ok"] and f.calls[2][3]["phone_number"] == "+1666"


def test_place_call_payload_and_log(env, tmp_path, monkeypatch):
    monkeypatch.setenv("ELEVENLABS_AGENT_ID", "ag_1")
    monkeypatch.setenv("ELEVENLABS_PHONE_NUMBER_ID", "ph1")
    f = Fake([(200, {"success": True, "conversation_id": "conv_1", "callSid": "x"})])
    r = C.place_call(SUG, "+358 45 129 1684", api=C.Api("secretkey", f))
    assert r == {"ok": True, "conversation_id": "conv_1"}
    p = f.calls[0][3]
    assert f.calls[0][1].endswith(("/v1/convai/twilio/outbound-call", "/v1/convai/sip-trunk/outbound-call"))
    assert p["to_number"] == "+358451291684" and p["agent_id"] == "ag_1" and p["agent_phone_number_id"] == "ph1"
    dv = p["conversation_initiation_client_data"]["dynamic_variables"]
    assert dv["holiday_date_fi"] == "24.12." and dv["proposed_hours"] == "9-13" and dv["suggestion_id"] == "sg-1"
    assert dv["business_name"] == "Furry Paw Vet Clinic" and dv["holiday_name_fi"] == "jouluaatto"
    log = (tmp_path / "call_log.jsonl").read_text()
    assert "conv_1" in log and "secretkey" not in log and "451291684" not in log


def test_place_call_failure(env, monkeypatch):
    monkeypatch.setenv("ELEVENLABS_AGENT_ID", "ag_1")
    monkeypatch.setenv("ELEVENLABS_PHONE_NUMBER_ID", "ph1")
    r = C.place_call(SUG, api=C.Api("k", Fake([(422, {"detail": "bad number"})])))
    assert r["ok"] is False and "422" in r["error"]


def test_dry_run_unconfigured(env):
    assert C.place_call(SUG, "+358451291684", api=C.Api("k", Fake([]))) == {"ok": False, "reason": "call lane not configured"}


def test_ladder_signature_compat(env):
    assert C.place_call(SUG)["reason"] == "call lane not configured"  # ladder calls place_call(s) with one arg


# ---- webhook parsing

@pytest.mark.parametrize("text,expect", [
    ("Kyllä, hyväksyn", {"action": "approve"}),
    ("joo sopii", {"action": "approve"}),
    ("Ei kiitos", {"action": "decline"}),
    ("ei", {"action": "decline"}),
    ("yhdeksästä yhteen", {"action": "edit", "edited": [{"start": "09:00", "end": "13:00"}]}),
    ("kymmenestä kahteen", {"action": "edit", "edited": [{"start": "10:00", "end": "14:00"}]}),
    ("9-13", {"action": "edit", "edited": [{"start": "09:00", "end": "13:00"}]}),
    ("klo 8.30 - 12", {"action": "edit", "edited": [{"start": "08:30", "end": "12:00"}]}),
    ("ollaan kiinni", {"action": "edit", "edited": "closed"}),
    ("suljettu", {"action": "edit", "edited": "closed"}),
    ("hmm en tiedä", {"action": "decline"}),
    ("mitä sanoit", None),
])
def test_parse_utterance(text, expect):
    assert CR.parse_utterance(text) == expect


def payload(sid="sg-1", transcript=None, analysis=None, typ="post_call_transcription"):
    return {"type": typ, "data": {"conversation_id": "conv_1", "transcript": transcript or [], "analysis": analysis or {},
                                  "conversation_initiation_client_data": {"dynamic_variables": {"suggestion_id": sid, "business_id": "SinceAI07"}}}}


def run(p):
    return asyncio.run(CR.handle_payload(p))


def tr(user_last):
    return [{"role": "agent", "message": "Hei, onko hetki aikaa?"}, {"role": "user", "message": "ei ole kiire, kerro vain"},
            {"role": "agent", "message": "Jouluaatto on 24.12. Hyväksytkö?"}, {"role": "user", "message": user_last},
            {"role": "agent", "message": "Kiitos."}, {"role": "user", "message": "Moi"}]


def test_webhook_three_outcomes_via_transcript(env):
    for i, (said, action, edited) in enumerate([("Kyllä", "approve", None), ("ei kiitos", "decline", None),
                                                 ("yhdeksästä yhteen", "edit", [{"start": "09:00", "end": "13:00"}])]):
        sid = f"sg-t{i}"
        r = run(payload(sid, tr(said)))
        d = r["decision"]
        assert d["action"] == action and d["edited"] == edited and d["via"] == "call" and d["suggestion_id"] == sid
        assert R.is_decided(sid)


def test_webhook_structured_analysis_wins(env):
    a = {"data_collection_results": {"action": {"value": "edit"}, "hours": {"value": "10:00-14:00"}}}
    d = run(payload("sg-a", tr("kyllä"), a))["decision"]
    assert d["action"] == "edit" and d["edited"] == [{"start": "10:00", "end": "14:00"}]


def test_webhook_first_turn_no_is_not_a_decline(env):
    t = [{"role": "agent", "message": "onko hetki aikaa?"}, {"role": "user", "message": "ei oikein"},
         {"role": "agent", "message": "Hyväksytkö?"}]
    assert run(payload("sg-n", t))["decision"] is None


def test_webhook_already_decided_and_failure(env):
    run(payload("sg-d", tr("kyllä")))
    assert run(payload("sg-d", tr("ei")))["ignored"] == "already decided"
    assert run(payload("sg-f", typ="call_initiation_failure"))["handled"] == "failure"


def test_signature():
    body = b'{"a":1}'
    h = CR.sign("sec", body, 1000)
    assert CR.signature_ok("sec", body, h, now=1100)
    assert not CR.signature_ok("sec", body, h, now=1000 + 99999)
    assert not CR.signature_ok("other", body, h, now=1100)
    assert not CR.signature_ok("sec", body + b" ", h, now=1100)


def test_http_endpoint_with_hmac(env, monkeypatch):
    from fastapi import FastAPI
    from fastapi.testclient import TestClient
    monkeypatch.setenv("ELEVENLABS_WEBHOOK_SECRET", "sec")
    app = FastAPI()
    app.include_router(CR.router)
    c = TestClient(app)
    body = json.dumps(payload("sg-h", tr("kyllä"))).encode()
    assert c.post("/webhooks/call", content=body).status_code == 401
    r = c.post("/webhooks/call", content=body, headers={"elevenlabs-signature": CR.sign("sec", body)})
    assert r.status_code == 200 and r.json()["decision"] == "approve"


def test_router_registered_in_app():
    from fastapi.testclient import TestClient
    from kaiku.app import app
    r = TestClient(app).post("/webhooks/call", content=b"not json")
    assert r.status_code in (400, 401), r.text[:200]
