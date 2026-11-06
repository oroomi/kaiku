"""Voice tests. Fake store, fake chain, fake clock and a fake Anthropic client; live API tests only with KAIKU_LIVE_VOICE=1."""
import asyncio
import json
import os
import types
from datetime import date

import httpx
import pytest
from fastapi.testclient import TestClient

from kaiku.app import app
from kaiku.voice import brain, stt, tts
from kaiku.voice.tools import Tools

SECRET_A, SECRET_E = "sk-ant-TESTSECRET123", "xi-TESTSECRET456"
BIZ = {"id": "furry-paw", "name": "Furry Paw Vet Clinic", "address": "Tikkurilantie 9, Vantaa", "city": "Vantaa", "lat": 1, "lon": 2, "category": "veterinary",
       "regular_hours": {"mon": [{"start": "09:00", "end": "17:00"}], "tue": [], "wed": [], "thu": [{"start": "09:00", "end": "17:00"}], "fri": [], "sat": [], "sun": []},
       "last_year_exceptions": [{"date": "2025-12-24", "hours": [{"start": "09:00", "end": "13:00"}]}], "website": None, "owner_whatsapp": None, "source": "sample"}
SUG = {"id": "s1", "business_id": "furry-paw", "holiday_date": "2026-12-24", "kind": "hours", "proposed": [{"start": "09:00", "end": "13:00"}], "confidence": 0.92,
       "reasons": [{"source": "last_year", "dataset_id": "x", "text_fi": "Viime vuonna 9-13.", "text_en": "Last year 9-13."}], "message_fi": "Jouluaattona auki 9-13.",
       "message_en": "Open 9-13 on Christmas Eve.", "status": "proposed", "channel_log": []}


class M(dict):
    def model_dump(self, mode=None):
        return dict(self)


class FakeStore:
    def get_business(self, bid): return M(BIZ) if bid == "furry-paw" else None
    def list_suggestions(self, bid, limit=5): return [M(SUG)] if bid == "furry-paw" else []
    def recent_events(self, n): return [types.SimpleNamespace(ts="2026-11-06T10:00:00Z", step="detect", title_fi="Tunnistettu", title_en="Detected")]


class FakeChain:
    STEPS = {}
    calls = []
    async def api_run(self, business, date):
        self.calls.append((business, date)); return {"suggestion_id": "abc123"}


class FakeClock:
    d = date(2026, 11, 2)
    def today(self): return self.d
    def set_today(self, d): self.d = d
    def clear(self): self.d = date(2026, 11, 6)
    def is_fake(self): return True


class FakeHolidays:
    def upcoming(self, today, days=21):
        h = types.SimpleNamespace(date="2026-11-08", name_fi="Isänpäivä", name_en="Father's Day", public_holiday=False, weekday="sun")
        return [h] if today <= date(2026, 11, 8) else []


def mk_tools():
    return Tools(store=FakeStore(), chain=FakeChain(), clock=FakeClock(), holidays=FakeHolidays(), gateway=None)


def run(c): return asyncio.run(c)


# ---------- tools ----------
def test_tool_shapes():
    t = mk_tools()
    b = run(t.get_business("furry-paw"))
    assert b["name"].startswith("Furry Paw") and b["regular_hours"]["sun"] == "closed" and b["last_year_exceptions"][0]["hours"] == "9-13"
    assert b["upcoming_holidays"][0]["name_fi"] == "Isänpäivä" and b["upcoming_holidays"][0]["regular_hours_that_day"] == "closed"
    assert {"type": "spotlight", "selector": '[data-pilot="suggestions"]'} in b["_actions"]
    s = run(t.get_suggestions("furry-paw"))
    assert s["suggestions"][0]["proposed_hours"] == "9-13" and s["suggestions"][0]["confidence"] == 0.92
    assert run(t.get_suggestions("nope"))["error"]
    assert run(t.get_events(5))["events"][0]["step"] == "detect"
    assert run(t.get_today())["today"] == "2026-11-02"


def test_run_chain_and_timetravel():
    t = mk_tools()
    r = run(t.run_chain("furry-paw", "2026-12-24"))
    assert r["started"] and r["suggestion_id"] == "abc123" and t.chain.calls == [("furry-paw", "2026-12-24")]
    assert any(a["type"] == "run_chain" for a in r["_actions"])
    assert run(t.run_chain("furry-paw", "tomorrow"))["error"]
    assert run(t.run_chain("ghost", "2026-12-24"))["error"]
    tt = run(t.timetravel("2026-11-02"))
    assert tt["today"] == "2026-11-02" and tt["will_detect_within_21_days"][0]["public_holiday"] is False
    assert run(t.timetravel("garbage"))["error"]


def test_call_dispatch_and_broker_guard():
    t = mk_tools()
    assert "get_entity" not in {s["name"] for s in t.specs()}      # no gateway: no broker tools, voice still works
    assert run(t.call("get_entity", {"id": "x"}))["error"]
    assert run(t.call("get_business", {"bogus": 1}))["error"]     # bad args never raise
    names = {s["name"] for s in Tools(store=FakeStore(), chain=FakeChain(), clock=FakeClock(), holidays=FakeHolidays(), gateway=object()).specs()}
    assert {"list_entities", "get_entity", "propose_update"} <= names
    assert not names & {"approve", "reject"}                       # agents may only propose


# ---------- brain with a fake Anthropic client ----------
def blk(**k): return types.SimpleNamespace(**k)


class FakeAnthropic:
    def __init__(self, script):
        self.script, self.n, self.seen = script, 0, []
        self.messages = self
    async def create(self, **kw):
        self.seen.append(kw); r = self.script[min(self.n, len(self.script) - 1)]; self.n += 1; return r


def test_ask_loop_runs_tools_and_returns_actions():
    script = [types.SimpleNamespace(stop_reason="tool_use", content=[blk(type="tool_use", id="t1", name="get_business", input={"business_id": "furry-paw"}),
                                                                      blk(type="tool_use", id="t2", name="get_suggestions", input={"business_id": "furry-paw"})]),
              types.SimpleNamespace(stop_reason="end_turn", content=[blk(type="text", text="Jouluaattona puuttuu aukiolo, ehdotus 9-13.")])]
    fc = FakeAnthropic(script)
    r = run(brain.ask("Kaiku, what's wrong with Furry Paw?", client=fc, tools=mk_tools()))
    assert r["text"].startswith("Jouluaattona") and r["tools"] == ["get_business", "get_suggestions"] and r["steps"] == 2
    assert r["actions"] == [{"type": "navigate", "url": "/"}, {"type": "spotlight", "selector": '[data-pilot="hero"]'}]
    assert fc.seen[0]["model"] == "claude-sonnet-5-5"
    tr = fc.seen[1]["messages"][-2]["content"]  # the list is shared, so the final reply was appended after
    assert len(tr) == 2 and all(x["type"] == "tool_result" for x in tr) and "_actions" not in tr[0]["content"]


def test_ask_loop_caps_at_six_steps_and_says_unknown():
    loop = types.SimpleNamespace(stop_reason="tool_use", content=[blk(type="tool_use", id="t", name="get_today", input={})])
    fc = FakeAnthropic([loop])
    r = run(brain.ask("x", lang="en", client=fc, tools=mk_tools()))
    assert fc.n == 6 and r["steps"] == 6 and r["text"] == "I do not know."


def test_ask_empty_text():
    assert run(brain.ask("  ", client=FakeAnthropic([]), tools=mk_tools()))["text"] == ""


# ---------- routes ----------
@pytest.fixture
def client(monkeypatch, tmp_path):
    monkeypatch.setenv("ANTHROPIC_API_KEY", SECRET_A)
    monkeypatch.setenv("ELEVENLABS_API_KEY", SECRET_E)
    monkeypatch.setenv("ELEVENLABS_VOICE_ID", "voiceX")
    monkeypatch.setattr(tts, "CACHE", tmp_path)
    return TestClient(app)


def test_routes_reject_empty(client):
    assert client.post("/api/voice/stt", content=b"", headers={"content-type": "audio/webm"}).status_code == 400
    assert client.post("/api/voice/stt", content=b"x" * 100, headers={"content-type": "audio/webm"}).status_code == 400
    assert client.post("/api/voice/tts", json={"text": "   "}).status_code == 400
    assert client.post("/api/voice/tts", json={}).status_code == 400
    assert client.post("/api/voice/ask", json={"text": ""}).status_code == 400


def _mock(handler):
    real = httpx.AsyncClient
    return lambda *a, **k: real(transport=httpx.MockTransport(handler))


def test_tts_and_stt_proxy_never_leak_keys(client, monkeypatch, tmp_path):
    seen = {}
    def handler(req):
        seen[req.url.path] = req.headers.get("xi-api-key")
        if "text-to-speech" in req.url.path:
            assert json.loads(req.content)["model_id"] == "eleven_flash_v2_5" and "voiceX" in req.url.path
            return httpx.Response(200, content=b"ID3fakeaudio")
        return httpx.Response(200, json={"text": "Terve Kaiku", "language_code": "fin"})
    monkeypatch.setattr(tts.httpx, "AsyncClient", _mock(handler))
    monkeypatch.setattr(stt.httpx, "AsyncClient", _mock(handler))
    r1 = client.post("/api/voice/tts", json={"text": "Jouluaattona auki 9-13."})
    r2 = client.post("/api/voice/tts", json={"text": "Jouluaattona auki 9-13."})
    assert r1.status_code == 200 and r1.headers["content-type"] == "audio/mpeg" and r1.content == b"ID3fakeaudio"
    assert r1.headers["x-tts-cache"] == "miss" and r2.headers["x-tts-cache"] == "hit" and len(list(tmp_path.glob("*.mp3"))) == 1
    r3 = client.post("/api/voice/stt", content=b"x" * 3000, headers={"content-type": "audio/webm;codecs=opus"})
    assert r3.status_code == 200 and r3.json()["text"] == "Terve Kaiku"
    assert all(v == SECRET_E for v in seen.values())               # keys go upstream only
    for r in (r1, r2, r3):
        blob = r.text if r.headers["content-type"].startswith("application/json") else str(r.headers)
        assert SECRET_E not in blob and SECRET_A not in blob and SECRET_E not in str(r.headers)


def test_upstream_failure_is_a_clean_status(client, monkeypatch):
    monkeypatch.setattr(tts.httpx, "AsyncClient", _mock(lambda req: httpx.Response(401, text="bad key xi-TESTSECRET456")))
    r = client.post("/api/voice/tts", json={"text": "hei"})
    assert r.status_code == 502 and SECRET_E not in r.text


def test_ask_route_error_hides_details(client, monkeypatch):
    async def boom(*a, **k): raise RuntimeError("secret " + SECRET_A)
    monkeypatch.setattr(brain, "ask", boom)
    r = client.post("/api/voice/ask", json={"text": "hei"})
    assert r.status_code == 200 and r.json()["error"] is True and SECRET_A not in r.text


def test_every_page_has_orb_and_nav(client, monkeypatch):
    from kaiku import store
    monkeypatch.setattr(store, "get_business", lambda bid: None)
    html = client.get("/").text
    assert 'id="kv-orb"' in html and "/static/voice.js" in html  # the home has the orb and the nav
    assert 'href="/map"' in html
    j = client.get("/judge", headers={"x-kaiku-key": "testkey"}).text
    assert 'id="kv-orb"' in j and 'href="/map"' in j and 'href="/room"' in j
    assert SECRET_A not in html and SECRET_E not in html


# ---------- live (real APIs): KAIKU_LIVE_VOICE=1 ----------
live = pytest.mark.skipif(os.getenv("KAIKU_LIVE_VOICE") != "1", reason="set KAIKU_LIVE_VOICE=1 for real API calls")


@live
def test_live_tts_then_stt_roundtrip():
    from dotenv import load_dotenv
    load_dotenv(os.path.join(os.path.dirname(__file__), "..", ".env"))
    import time
    t0 = time.perf_counter(); audio, _ = run(tts.synthesize("Jouluaattona klinikka on auki yhdeksästä kolmeen.", cache_dir=__import__("pathlib").Path("/tmp/kv_tts_test")))
    t_tts = time.perf_counter() - t0
    t0 = time.perf_counter(); out = run(stt.transcribe(audio, "audio/mpeg")); t_stt = time.perf_counter() - t0
    print(f"tts {t_tts:.2f}s stt {t_stt:.2f}s -> {out}")
    assert "jouluaatto" in out["text"].lower() and t_stt < 2.5


@live
def test_live_demo_line_what_is_wrong():
    from dotenv import load_dotenv
    load_dotenv(os.path.join(os.path.dirname(__file__), "..", ".env"))
    r = run(brain.ask("Kaiku, what's wrong with Furry Paw?"))
    print(r)
    assert "get_suggestions" in r["tools"] and any(a["type"] == "spotlight" for a in r["actions"])


def test_cap_words_sentence_boundary():
    from kaiku.voice.brain import cap_words
    short = "Ehdotan 9-13. Google näyttää 9-17."
    assert cap_words(short) == short
    long = "First sentence has seven words here. " + " ".join(["more"] * 40) + "."
    out = cap_words(long)
    assert out == "First sentence has seven words here." and len(out.split()) <= 30
    run_on = " ".join(["word"] * 50)
    out = cap_words(run_on)
    assert len(out.split()) == 30 and out.endswith(".")
