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
    from kaiku.schema import Reason
    s = Suggestion(id="sg1", business_id="furry-paw", holiday_date="2026-12-24", kind="hours",
                   proposed=[Span(start="09:00", end="13:00")], confidence=0.9,
                   reasons=[Reason(source="last_year", dataset_id="x", text_fi="Viime jouluaattona olitte auki 9-13.",
                                   text_en="Last Christmas Eve you were open 9-13.")])
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
    assert r.status_code == 200 and "Furry Paw Vet Clinic" in r.text
    # English by default
    assert "Christmas Eve, Thursday 24.12.: open 9-13" in r.text and "Last Christmas Eve you were open 9-13." in r.text
    assert ">Approve<" in r.text and ">Edit<" in r.text and ">No thanks<" in r.text and "WHY" in r.text
    for fi in ("Hyväksy", "Muokkaa", "Ei kiitos", "MIKSI", "Jouluaattona"):
        assert fi not in r.text, fi
    for pilot in ("decide-page", "proposal", "approve", "edit", "decline", "standing-permission", "why"):
        assert f'data-pilot="{pilot}"' in r.text
    assert 'data-lang="en"' in r.text
    assert "—" not in r.text and "–" not in r.text.replace("&ndash;", "")
    j = c.get("/api/decide/" + _tok(s)).json()
    assert j["sentence_fi"].startswith("Jouluaattona") and j["lang"] == "en"
    assert j["sentence_en"] == "Christmas Eve, Thursday 24.12.: open 9-13"


def test_finnish_page_when_owner_language_fi(env):
    from kaiku import store
    c, s = env
    b = store.get_business("furry-paw")
    store.save_business(b.model_copy(update={"owner_language": "fi"}))
    r = c.get("/d/" + _tok(s))
    assert r.status_code == 200 and 'data-lang="fi"' in r.text
    assert "Jouluaattona 24.12. auki klo 9-13" in r.text and "Hyväksy" in r.text and "MIKSI" in r.text
    assert "Kiitos, tehty" not in r.text


def test_english_missing_and_done_states(env):
    c, s = env
    assert "This link does not work." in c.get("/d/nope").text
    t = _tok(s)
    assert c.post(f"/api/decide/{t}", json={"action": "decline"}).status_code == 200
    page = c.get("/d/" + t).text
    assert "Thank you, done." in page and "DONE" in page and "Kiitos" not in page


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
    assert "Thank you, done." in c.get("/d/" + t).text


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


def test_ghost_suggestion_404_no_event(env):
    from kaiku import store
    c, s = env
    t = _tok(s)
    before = len(store.recent_events(50))
    import kaiku.decide.router as rt
    orig = rt.store.get_suggestion
    rt.store.get_suggestion = lambda sid: None
    try:
        r = c.post(f"/api/decide/{t}", json={"action": "approve"})
    finally:
        rt.store.get_suggestion = orig
    assert r.status_code == 404 and r.json()["message_fi"] == "Ehdotusta ei löydy."
    assert len(store.recent_events(50)) == before
    assert c.post(f"/api/decide/{t}", json={"action": "approve"}).status_code == 200


def test_late_post_after_timeout_410(env, monkeypatch):
    from kaiku import store
    from kaiku.decide import step
    c, s = env
    monkeypatch.setenv("KAIKU_DECIDE_TIMEOUT_S", "0.05")
    t = _tok(s)
    assert asyncio.run(step.decide_step(s)).action == "timeout"
    assert store.get_suggestion("sg1").status == "expired"
    r = c.post(f"/api/decide/{t}", json={"action": "approve"})
    assert r.status_code == 410 and r.json()["state"] == "expired"
    assert r.json()["message_fi"] == "Ehdotus vanheni ennen päätöstä. Kaiku lähettää uuden ehdotuksen."
    page = c.get("/d/" + t).text
    assert "The suggestion expired before a decision." in page and "Thank you, done." not in page
    assert not [e for e in store.recent_events(50) if e.suggestion_id == "sg1" and "Omistaja" in e.title_fi]


def test_late_post_honoured_only_when_chain_accepts(env, monkeypatch):
    from kaiku import chain, store
    from kaiku.decide import step
    c, s = env
    monkeypatch.setenv("KAIKU_DECIDE_TIMEOUT_S", "0.05")
    t = _tok(s)
    asyncio.run(step.decide_step(s))
    calls = []
    monkeypatch.setattr(chain, "on_decision", lambda d: calls.append(d) or False, raising=False)
    assert c.post(f"/api/decide/{t}", json={"action": "approve"}).status_code == 410
    monkeypatch.setattr(chain, "on_decision", lambda d: calls.append(d) or True, raising=False)
    r = c.post(f"/api/decide/{t}", json={"action": "approve"})
    assert r.status_code == 200 and r.json()["late"] is True and r.json()["next"] == "apply" and len(calls) == 2
