"""Owner chat: fallback parser, opening messages from a stub feed, decisions reaching the chain with a fake Yext."""
import asyncio
import json
import os

os.environ.setdefault("OWNER_WHATSAPP", "+358000000000")  # same as test_core: settings are read at first import

import pytest
from fastapi.testclient import TestClient

from kaiku import chain, store
from kaiku.chat import actions, brain, feed, feed_stub, router as chat_router
from kaiku.chat import parser as P

FEED = {"suggestions": [
    {"id": "t-hours", "kind": "holiday_hours", "title_en": "Christmas Eve 24.12. hours are missing",
     "text_en": "Last year you were open 9-13. Connect still publishes 9-17.", "proposed": [{"start": "09:00", "end": "13:00"}],
     "confidence": 0.8, "status": "proposed", "holiday_date": "2026-12-24", "holiday_name_en": "Christmas Eve",
     "last_year": [{"start": "09:00", "end": "13:00"}], "reasons": [{"source": "last_year", "text_en": "Last year 9-13"}]},
    {"id": "t-conflict", "kind": "conflict", "title_en": "Two sources disagree", "text_en": "Website says closed.", "proposed": None,
     "confidence": 0.5, "status": "proposed", "holiday_date": "2026-12-24", "reasons": []},
    {"id": "t-nochange", "kind": "no_change", "title_en": "Father's Day 8.11.",
     "text_en": "Father's Day 8.11. is not a public holiday and you are closed on Sundays. Nothing to change.", "proposed": None,
     "confidence": 0.95, "status": "proposed", "holiday_date": "2026-11-08", "reasons": []},
]}


@pytest.fixture
def stub_feed(monkeypatch, tmp_path):
    from kaiku.learn import timetravel
    timetravel.clear()
    f = tmp_path / "feed.json"
    f.write_text(json.dumps(FEED))
    monkeypatch.setenv("KAIKU_FEED_FIXTURE", str(f))
    monkeypatch.setenv("KAIKU_CHAT_NO_LLM", "1")  # deterministic fallback, no network
    monkeypatch.setenv("KAIKU_DATA_DIR", str(tmp_path))
    from kaiku.config import settings
    old_db = settings.DB_PATH
    store.reset(tmp_path / "chat.sqlite")
    store.seed()
    chat_router._sessions.clear()
    # the fixture feed is static, so make statuses follow the stored suggestions the way the real feed does
    real = feed_stub.get_feed

    def live(bid):
        d = json.loads(f.read_text())
        for it in d["suggestions"]:
            s = store.get_suggestion(it["id"])
            if s:
                it["status"] = {"approved": "approved", "edited": "approved", "applied": "approved", "declined": "declined"}.get(s.status, "proposed")
        return d
    monkeypatch.setattr(feed_stub, "get_feed", live)
    yield f
    store.reset(old_db)


# ---------- fallback parser ----------
@pytest.mark.parametrize("text,want", [
    ("yes", {"action": "approve"}), ("Yes, do it", {"action": "approve"}), ("I agree", {"action": "approve"}), ("ok", {"action": "approve"}),
    ("approve", {"action": "approve"}), ("no", {"action": "decline"}), ("No thanks", {"action": "decline"}),
    ("closed", {"action": "edit", "edited": "closed"}),
    ("make it 10-14", {"action": "edit", "edited": [{"start": "10:00", "end": "14:00"}]}),
    ("9 to 1", {"action": "edit", "edited": [{"start": "09:00", "end": "13:00"}]}),
    ("let's do 8:30-16", {"action": "edit", "edited": [{"start": "08:30", "end": "16:00"}]}),
    ("Change the hours", {"action": "change"}), ("what is the weather", None), ("", None)])
def test_fallback_parser(text, want):
    assert P.parse(text) == want


# ---------- opening messages ----------
def test_opening_from_feed(stub_feed):
    ms = chat_router.opening("furry-paw")
    assert ms[0]["kind"] == "intro" and ms[0]["text"] == "Hi Furry Paw Vet Clinic. I noticed 2 things."
    sug = [m for m in ms if m["kind"] == "suggestion"]
    assert [m["suggestion_id"] for m in sug] == ["t-hours", "t-conflict"]
    assert "I suggest 9-13" in sug[0]["text"] and sug[0]["proposed"] == "9-13"
    note = [m for m in ms if m["kind"] == "note"][0]  # reliability: nothing to change, and why
    assert "Nothing to change" in note["text"] and "Sundays" in note["text"]
    assert not any("—" in m["text"] for m in ms)


def test_stub_used_only_without_real_feed(monkeypatch):
    called = {}
    monkeypatch.setattr(feed_stub, "get_feed", lambda b: called.setdefault("stub", {"suggestions": []}))
    import sys, types
    monkeypatch.setitem(sys.modules, "kaiku.suggest.feed", types.SimpleNamespace(get_feed=lambda b: {"suggestions": [{"id": "real"}]}))
    assert feed.get_feed("furry-paw") == {"suggestions": [{"id": "real"}]} and not called
    monkeypatch.setitem(sys.modules, "kaiku.suggest.feed", None)  # import fails
    assert feed.get_feed("furry-paw") == {"suggestions": []} and called


def test_open_endpoint(stub_feed):
    from kaiku.app import app
    c = TestClient(app)
    j = c.get("/api/chat/open?business=furry-paw").json()
    assert j["messages"][0]["kind"] == "intro" and len(j["messages"]) == 4
    assert c.post("/api/chat", json={"message": "  ", "session": "x"}).status_code == 422


# ---------- decisions reach the chain's decide path with a fake Yext ----------
@pytest.fixture
def fake_yext(monkeypatch):
    writes = []

    def backend(entity_id, day, proposed):
        writes.append((entity_id, day, proposed))
        return {"yext_status": "ok", "verified": True, "entity_id": entity_id, "written": proposed}
    monkeypatch.setattr(chain, "apply_backend", backend)
    monkeypatch.setattr(chain, "whatsapp_configured", lambda: False)
    return writes


def test_approve_then_standing_permission(stub_feed, fake_yext):
    from kaiku.app import app
    c = TestClient(app)
    r = c.post("/api/chat", json={"message": "yes", "session": "s1"}).json()
    assert fake_yext == [("SinceAI07", "2026-12-24", [{"start": "09:00", "end": "13:00"}])]
    assert r["actions"][0]["type"] == "decided" and r["statuses"]["t-hours"] == "approved"
    assert "Last year 9-13, this year 9-13 again. Want me to do this every Christmas Eve?" in r["reply"]
    ev = [e for e in store.recent_events(50) if e.suggestion_id == "t-hours"]
    assert any(e.step == "decide" and (e.detail or {}).get("via") == "web" for e in ev) and any(e.step == "apply" for e in ev)
    assert store.get_decisions("t-hours")[0].via == "web"
    r2 = c.post("/api/chat", json={"message": "yes", "session": "s1"}).json()  # the follow-up answer, not another approval
    assert r2["actions"] == [{"type": "standing", "suggestion_id": "t-hours", "enabled": True}] and len(fake_yext) == 1
    from kaiku.learn import prefs
    assert prefs.get_prefs("furry-paw")["standing_permission"]["holiday"] == "christmaseve"


def test_edit_and_decline(stub_feed, fake_yext):
    from kaiku.app import app
    c = TestClient(app)
    r = c.post("/api/chat", json={"message": "make it 10-14", "session": "s2"}).json()
    assert fake_yext[-1][2] == [{"start": "10:00", "end": "14:00"}] and "10-14" in r["reply"] and "9-13" in r["reply"]
    assert store.get_suggestion("t-hours").status == "applied"
    n = len(fake_yext)
    r = c.post("/api/chat", json={"message": "no thanks", "session": "s2"}).json()  # follow-up declined: no standing permission
    assert "ask you each time" in r["reply"] and len(fake_yext) == n
    r = c.post("/api/chat", json={"message": "no", "session": "s2"}).json()  # now the conflict is under discussion
    assert r["statuses"]["t-conflict"] == "declined" and len(fake_yext) == n


def test_no_change_cannot_be_decided_and_garbage_asks(stub_feed, fake_yext):
    r = asyncio.run(actions.decide("furry-paw", "t-nochange", "approve"))
    assert r["ok"] is False and fake_yext == []
    r = asyncio.run(actions.decide("furry-paw", "t-hours", "edit", [{"start": "14:00", "end": "09:00"}]))
    assert r["ok"] is False and fake_yext == []
    from kaiku.app import app
    out = TestClient(app).post("/api/chat", json={"message": "tell me a joke", "session": "s3"}).json()
    assert "did not catch" in out["reply"] and out["actions"] == [] and fake_yext == []


def test_llm_failure_falls_back(stub_feed, fake_yext, monkeypatch):
    monkeypatch.delenv("KAIKU_CHAT_NO_LLM")
    monkeypatch.setenv("ANTHROPIC_API_KEY", "sk-test-not-real")

    async def boom(*a, **k):
        raise RuntimeError("api down")
    monkeypatch.setattr(brain, "llm_reply", boom)
    from kaiku.app import app
    r = TestClient(app).post("/api/chat", json={"message": "yes", "session": "s4"}).json()
    assert r["reply"].startswith("Done, Christmas Eve 9-13 is saved.") and len(fake_yext) == 1
    assert len(r["reply"].split()) <= 40


def test_reply_trim_keeps_follow_up():
    q = "Last year 9-13, this year 9-13 again. Want me to do this every Christmas Eve?"
    long = " ".join(["Saved the hours for you now."] * 8)
    body = brain.trim_words(long, 40 - len(q.split()))
    assert len((body + " " + q).split()) <= 42 and q.endswith("Eve?")


# ---------- drawer and judge are keyed ----------
def test_drawer_and_judge_keyed(stub_feed):
    from kaiku.app import app
    c = TestClient(app)
    home = c.get("/").text
    for word in ("Run the chain", "Reset demo", "time travel", "Today (time travel)"):
        assert word not in home
    assert c.get("/owner/drawer").status_code == 403 and c.get("/judge").status_code == 403
    assert "Owner view" not in c.get("/judge").text.replace("Back to the owner view", "")
    assert c.get("/api/chat/keyed").json() == {"keyed": False}
    k = TestClient(app, headers={"X-Kaiku-Key": "testkey"})
    assert k.get("/api/chat/keyed").json() == {"keyed": True}
    d = k.get("/owner/drawer")
    assert d.status_code == 200 and 'data-pilot="run-chain"' in d.text and 'id="tt-date"' in d.text and 'data-pilot="reset"' in d.text
    j = k.get("/judge")
    assert j.status_code == 200 and 'data-pilot="event-strip"' in j.text and 'href="/"' in j.text and "YEXT READ-BACK" in j.text
    assert c.get("/judge?key=testkey").status_code == 200 and c.get("/owner").status_code == 200
