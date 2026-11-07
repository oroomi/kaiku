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
    assert c.get("/api/chat/open?business=furry-paw").json()["messages"] == []   # the page's chat opens EMPTY
    j = c.get("/api/chat/open?business=furry-paw&full=1").json()               # the old opening stays available (WhatsApp, API)
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


H24 = "Christmas is coming. Do you want to change your hours on Christmas Eve 24.12. to 9-13? Everywhere Connect publishes still says 9-17."
RECUR = "You changed this last year as well. Do you want to make it recurring, this time of the year?"


def _chat(c, sid, text):
    return c.post("/api/chat", json={"message": text, "session": sid}).json()


def test_accept_hands_over_then_yes_applies_then_recurring_then_next(stub_feed, fake_yext):
    from kaiku.app import app
    c = TestClient(app)
    r = c.post("/api/suggestions/t-hours/accept", json={"session": "s1"}).json()
    assert r["reply"] == H24 and fake_yext == []                       # Accept writes nothing
    assert store.get_suggestion("t-hours") is None or store.get_suggestion("t-hours").status != "applied"
    r = _chat(c, "s1", "yes")
    assert fake_yext == [("SinceAI07", "2026-12-24", [{"start": "09:00", "end": "13:00"}])]
    assert r["reply"] == "Done. 24.12. 9-13 is saved and shows on Google, Fonecta Finder and 020202 within the hour. " + RECUR
    assert r["actions"][0]["type"] == "decided" and r["statuses"]["t-hours"] == "approved"
    ev = [e for e in store.recent_events(50) if e.suggestion_id == "t-hours"]
    assert any(e.step == "decide" and (e.detail or {}).get("via") == "web" for e in ev) and any(e.step == "apply" for e in ev)
    assert store.get_decisions("t-hours")[0].via == "web"
    r2 = _chat(c, "s1", "yes, every year")      # the recurring answer, NOT an approval of the next card
    assert r2["actions"] == [{"type": "standing", "suggestion_id": "t-hours", "enabled": True}] and len(fake_yext) == 1
    assert r2["reply"].startswith("Every Christmas Eve from now on, unless you tell me otherwise. Next: Two sources disagree.")
    assert r2["statuses"]["t-conflict"] == "proposed"
    from kaiku.learn import prefs
    assert prefs.get_prefs("furry-paw")["standing_permission"]["holiday"] == "christmaseve"


def test_recurring_question_only_with_last_year_data(stub_feed, fake_yext):
    from kaiku.app import app
    stub_feed.write_text(json.dumps({"suggestions": [
        {"id": "t-mid", "kind": "holiday_hours", "title_en": "Midsummer Eve 19.6.", "text_en": "x", "proposed": [{"start": "10:00", "end": "14:00"}],
         "confidence": 0.7, "status": "proposed", "holiday_date": "2027-06-18", "holiday_name_en": "Midsummer Eve", "reasons": []},
        {"id": "t-conflict", "kind": "conflict", "title_en": "Two sources disagree", "text_en": "x", "proposed": None, "confidence": 0.5,
         "status": "proposed", "holiday_date": "2026-12-26", "reasons": []}]}))
    c = TestClient(app)
    r = c.post("/api/suggestions/t-mid/accept", json={"session": "m1"}).json()
    assert r["reply"].startswith("Midsummer Eve is coming. Do you want to change your hours on Midsummer Eve 18.6. to 10-14?")
    out = _chat(c, "m1", "yes")["reply"]
    assert out.startswith("Done. 18.6. 10-14 is saved and shows on") and "recurring" not in out
    assert "Next: Two sources disagree." in out                          # no recurring question: straight to the next card


def test_suggest_a_change_flow(stub_feed, fake_yext):
    from kaiku.app import app
    c = TestClient(app)
    j = c.post("/api/suggestions/t-hours/change", json={"session": "c1"}).json()
    assert j["reply"] == ("You want to change Christmas Eve 24.12. hours are missing. I suggested 9-13 because last year 9-13. "
                          "What should it be?")
    r = _chat(c, "c1", "make it 10-14")
    assert r["reply"] == "10-14 on 24.12., shall I save it?" and fake_yext == []
    r = _chat(c, "c1", "yes")
    assert fake_yext == [("SinceAI07", "2026-12-24", [{"start": "10:00", "end": "14:00"}])]
    assert r["reply"].startswith("Done. 24.12. 10-14 is saved") and r["reply"].endswith(RECUR)
    assert store.get_suggestion("t-hours").status == "applied"
    n = len(fake_yext)
    r = _chat(c, "c1", "no thanks")                                       # recurring declined, no write
    assert r["reply"].startswith("Okay, I will ask you each time.") and len(fake_yext) == n


def test_no_at_any_point_leaves_it(stub_feed, fake_yext):
    from kaiku.app import app
    c = TestClient(app)
    c.post("/api/suggestions/t-hours/accept", json={"session": "n1"})
    r = _chat(c, "n1", "no")
    assert r["reply"] == "Okay, I leave it as it is." and r["statuses"]["t-hours"] == "declined" and fake_yext == []
    assert any(e.step == "learn" for e in store.recent_events(50) if e.suggestion_id == "t-hours")


def test_bare_yes_without_a_proposal_decides_nothing(stub_feed, fake_yext):
    from kaiku.app import app
    r = _chat(TestClient(app), "b1", "yes")
    assert "not proposed anything" in r["reply"] and r["actions"] == [] and fake_yext == []


def test_discard_route(stub_feed, fake_yext):
    from kaiku.app import app
    c = TestClient(app)
    r = c.post("/api/suggestions/t-hours/discard", json={"session": "d1"}).json()
    assert r["ok"] and r["reply"] == "Okay, I leave Christmas Eve 24.12. hours are missing as it is." and fake_yext == []
    assert r["actions"][0]["action"] == "decline" and store.get_decisions("t-hours")[0].via == "web"
    assert any(e.step == "learn" for e in store.recent_events(50) if e.suggestion_id == "t-hours")
    assert c.post("/api/suggestions/t-hours/discard", json={"session": "d1"}).json()["ok"] is False
    assert c.post("/api/suggestions/t-nochange/discard", json={"session": "d1"}).json()["ok"] is False
    assert any(m["text"].startswith("Okay, I leave") for m in c.get("/api/chat/open?session=d1").json()["messages"])


def test_text_kinds_proposals_and_honest_receipts(stub_feed, fake_yext, monkeypatch):
    from kaiku.app import app
    stub_feed.write_text(json.dumps({"suggestions": [
        {"id": "t-desc", "kind": "description", "title_en": "Typo in your description", "text_en": "x", "proposed": "We offer vaccination.",
         "typos": [{"wrong": "vacination", "right": "vaccination"}], "confidence": .9, "status": "proposed", "reasons": []},
        {"id": "t-nodesc", "kind": "description", "title_en": "No description", "text_en": "x", "proposed": "A small clinic.", "confidence": .9,
         "status": "proposed", "reasons": []},
        {"id": "t-rev", "kind": "review", "rating": 3, "title_en": "A 3-star review has no reply", "text_en": "x", "proposed": "Thank you, sorry about the wait.",
         "confidence": .7, "status": "proposed", "reasons": []}]}))
    calls = []
    monkeypatch.setattr(actions, "_text_apply", lambda item, text, client=None: calls.append((item["id"], text)) or
                        ({"yext_status": "ok", "verified": True} if item["kind"] == "description" else {"yext_status": "ok", "stored": True, "posted": False}))
    c = TestClient(app)
    assert c.post("/api/suggestions/t-desc/accept", json={"session": "x1"}).json()["reply"] == 'Shall I correct "vacination" to "vaccination" in your description?'
    assert c.post("/api/suggestions/t-nodesc/accept", json={"session": "x2"}).json()["reply"] == "Your listing has no description. Shall I publish this one? A small clinic."
    assert c.post("/api/suggestions/t-rev/accept", json={"session": "x3"}).json()["reply"] == 'Shall I post this reply to the 3-star review? "Thank you, sorry about the wait."'
    assert _chat(c, "x1", "yes")["reply"].startswith("Done. Your description is saved and shows on Google")
    r = _chat(c, "x3", "yes")["reply"]                       # stored, not posted: never claim a post
    assert r.startswith("Your reply is stored. The sandbox key cannot post review comments") and "posted" not in r.replace("cannot post", "")
    c.post("/api/suggestions/t-nodesc/change", json={"session": "x2"})   # the owner's own text replaces it
    assert _chat(c, "x2", "A friendly small animal clinic in Vantaa")["reply"] == 'Shall I save this as your description? "A friendly small animal clinic in Vantaa"'
    _chat(c, "x2", "yes")
    assert calls[-1] == ("t-nodesc", "A friendly small animal clinic in Vantaa")


def test_period_accept_sets_every_member_date(stub_feed, fake_yext):
    from kaiku.app import app
    mem = lambda d, n, p: {"date": d, "name_en": n, "kind": "closed" if p == "closed" else "hours", "proposed": p, "confidence": .7}
    stub_feed.write_text(json.dumps({"suggestions": [
        {"id": "t-period", "kind": "period", "title_en": "Christmas period: 3 dates", "text_en": "x", "confidence": .65, "status": "proposed",
         "holiday_date": "2026-12-24", "reasons": [], "proposed": [mem("2026-12-24", "Christmas Eve", [{"start": "09:00", "end": "13:00"}]),
                                                            mem("2026-12-25", "Christmas Day", "closed"), mem("2026-12-26", "St. Stephen's Day", "closed")]}]}))
    c = TestClient(app)
    r = c.post("/api/suggestions/t-period/accept", json={"session": "p1"}).json()
    assert r["reply"] == "The Christmas period is coming: 24.12. 9-13; 25.12. closed; 26.12. closed. Shall I set all of them?" and fake_yext == []
    out = _chat(c, "p1", "yes")
    assert [w[1] for w in fake_yext] == ["2026-12-24", "2026-12-25", "2026-12-26"]
    assert out["reply"].startswith("Done. All 3 dates are saved and show on Google, Fonecta Finder and 020202 within the hour.")


def test_failed_write_is_not_reported_as_saved(stub_feed, monkeypatch):
    monkeypatch.setattr(chain, "apply_backend", lambda e, d, p: {"yext_status": "error", "verified": False})
    monkeypatch.setattr(chain, "whatsapp_configured", lambda: False)
    from kaiku.app import app
    c = TestClient(app)
    c.post("/api/suggestions/t-hours/accept", json={"session": "f1"})
    r = _chat(c, "f1", "yes")["reply"]
    assert "saved" not in r.split("could not")[0] and "did not go through" in r


def test_edit_and_decline_legacy_focus(stub_feed, fake_yext):
    """A WhatsApp-style session (focus set by the opening, no stage): hours apply directly, a yes decides the focus."""
    from kaiku.app import app
    c = TestClient(app)
    chat_router.session("w1")["focus"] = "t-hours"
    r = _chat(c, "w1", "make it 10-14")
    assert fake_yext[-1][2] == [{"start": "10:00", "end": "14:00"}] and r["reply"].startswith("Done. 24.12. 10-14 is saved")


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
    c = TestClient(app)
    c.post("/api/suggestions/t-hours/accept", json={"session": "s4"})
    r = c.post("/api/chat", json={"message": "yes", "session": "s4"}).json()   # the deterministic stage handler needs no model
    assert r["reply"].startswith("Done. 24.12. 9-13 is saved") and len(fake_yext) == 1
    chat_router.session("s5")["focus"] = "t-conflict"    # free text goes to the model; it fails; the words after a decision still come from the apply result
    r = c.post("/api/chat", json={"message": "hmm, okay do it", "session": "s5"}).json()
    assert r["actions"] == [] or r["reply"].startswith(("Done", "I did not catch"))


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
    for word in ("Run the chain", "time travel", "Today (time travel)"):
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


def test_feed_overlay_shows_recorded_decisions(stub_feed, fake_yext):
    """The engine builds every card 'proposed'; the owner's recorded decisions are laid over a copy (cards, chat and /api/feed agree)."""
    from kaiku.chat.feed import with_decisions
    from kaiku.schema import Suggestion
    feed = {"business_id": "furry-paw", "suggestions": [
        {"id": "a", "kind": "holiday_hours", "holiday_date": "2026-12-24", "status": "proposed"},
        {"id": "b", "kind": "conflict", "holiday_date": "2026-12-24", "status": "proposed"},
        {"id": "c", "kind": "period", "status": "proposed", "proposed": [{"date": "2026-12-24"}, {"date": "2026-12-25"}]}]}
    assert [i["status"] for i in with_decisions(feed)["suggestions"]] == ["proposed"] * 3
    store.save_suggestion(Suggestion(id="a", business_id="furry-paw", holiday_date="2026-12-24", kind="hours", status="applied", confidence=.7,
                                     reasons=[], message_fi="", message_en=""))
    out = [i["status"] for i in with_decisions(feed)["suggestions"]]
    assert out == ["approved", "proposed", "proposed"] and feed["suggestions"][0]["status"] == "proposed"


# ---------- card actions: Accept (the chat's decide path) and Suggest a change (chat context) ----------


def test_suggest_change_errors(stub_feed, fake_yext):
    from kaiku.app import app
    c = TestClient(app)
    assert c.post("/api/suggestions/t-nochange/change", json={"session": "card2"}).status_code == 409
    assert c.post("/api/suggestions/nope/change", json={"session": "card2"}).status_code == 404
    assert c.post("/api/suggestions/t-nochange/accept", json={"session": "card2"}).json()["ok"] is False
