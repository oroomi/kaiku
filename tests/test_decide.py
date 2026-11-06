import asyncio
import importlib

import pytest
from fastapi.testclient import TestClient

from kaiku.schema import Suggestion, Span


@pytest.fixture()
def env(tmp_path, monkeypatch):
    monkeypatch.setenv("KAIKU_DATA_DIR", str(tmp_path))
    monkeypatch.setenv("PUBLIC_URL", "http://test")
    from kaiku import store
    store.reset(tmp_path / "k.sqlite")
    store.seed()
    s = Suggestion(id="sg1", business_id="furry-paw", holiday_date="2026-12-24", kind="hours",
                   proposed=[Span(start="09:00", end="13:00")], confidence=0.9)
    store.save_suggestion(s)
    from kaiku.app import app
    from kaiku.decide import step
    step._waiting.clear()
    yield TestClient(app), s
    store.reset()


def _tok(s):
    from kaiku.decide import tokens
    return tokens.issue(s.id, s.business_id)


def test_token_issue_lookup_used(env):
    from kaiku.decide import tokens
    _, s = env
    t = tokens.issue(s.id, s.business_id)
    assert len(t) >= 21 and tokens.issue(s.id, s.business_id) == t
    assert tokens.lookup(t) == {"suggestion_id": "sg1", "business_id": "furry-paw", "used": False, "expired": False, "decision": None}
    assert tokens.link_for(s.id, s.business_id) == "http://test/d/" + t
    assert tokens.mark_used(t, {"action": "approve"}) and not tokens.mark_used(t)
    assert tokens.lookup(t)["used"] and tokens.lookup("nope") is None


def test_bad_token_404_and_page_renders(env):
    c, s = env
    assert c.get("/d/nope").status_code == 404
    r = c.get("/d/" + _tok(s))
    assert r.status_code == 200 and "Furry Paw Vet Clinic" in r.text and "Jouluaattona 24.12. auki klo 9-13" in r.text
    assert "—" not in r.text and "–" not in r.text.replace("&ndash;", "")
    assert c.get("/api/decide/" + _tok(s)).json()["sentence_fi"].startswith("Jouluaattona")


def test_approve_resolves_waiting_future(env):
    from kaiku.decide import step
    c, s = env
    t = _tok(s)

    async def go():
        task = asyncio.create_task(step.decide_step(s))
        await asyncio.sleep(0.1)
        assert step.pending() == ["sg1"]
        r = await asyncio.to_thread(c.post, f"/api/decide/{t}", json={"action": "approve", "standing_permission": True, "scope": "all"})
        return r, await asyncio.wait_for(task, 3)
    r, d = asyncio.run(go())
    assert r.status_code == 200 and r.json()["next"] == "apply" and r.json()["waiting_chain"] is True
    assert d.action == "approve" and d.standing_permission and d.via == "web"
    assert r.json()["decision"]["scope"] == "all"
    assert step.pending() == [] and step.resolve("sg1", {}) is False
    assert c.post(f"/api/decide/{t}", json={"action": "approve"}).status_code == 409
    assert "Kiitos, tehty" in c.get("/d/" + t).text


def test_edit_validation(env):
    c, s = env
    t = _tok(s)
    for bad in [{"action": "edit"}, {"action": "edit", "edited": []},
                {"action": "edit", "edited": [{"start": "13:00", "end": "09:00"}]},
                {"action": "edit", "edited": [{"start": "9:00", "end": "13:00"}]},
                {"action": "edit", "edited": [{"start": "09:00", "end": "25:00"}]}]:
        assert c.post(f"/api/decide/{t}", json=bad).status_code == 422, bad
    r = c.post(f"/api/decide/{t}", json={"action": "edit", "edited": [{"start": "10:00", "end": "14:00"}]})
    assert r.status_code == 200 and r.json()["decision"]["edited"] == [{"start": "10:00", "end": "14:00"}]
    assert any(e.step == "decide" and "muokkasi" in e.title_fi for e in __import__("kaiku.store", fromlist=["x"]).recent_events(20))


def test_edit_closed_and_decline_chip(env):
    c, s = env
    r = c.post(f"/api/decide/{_tok(s)}", json={"action": "edit", "edited": "closed"})
    assert r.json()["decision"]["edited"] == "closed"
    from kaiku.decide import tokens
    t2 = tokens.issue("sg1", "furry-paw")
    r = c.post(f"/api/decide/{t2}", json={"action": "decline", "reason_chip": "Ajat ovat väärin", "standing_permission": True})
    d = r.json()
    assert d["next"] == "skip" and d["decision"]["reason_chip"] == "Ajat ovat väärin" and d["decision"]["standing_permission"] is False


def test_standing_scope_same_default(env):
    c, s = env
    r = c.post(f"/api/decide/{_tok(s)}", json={"action": "approve", "standing_permission": True})
    assert r.json()["decision"]["scope"] == "same" and r.json()["decision"]["standing_permission"] is True


def test_timeout(env, monkeypatch):
    from kaiku.decide import step
    monkeypatch.setenv("KAIKU_DECIDE_TIMEOUT_S", "0.05")
    _, s = env
    d = asyncio.run(step.decide_step(s))
    assert d.action == "timeout" and step.pending() == []
