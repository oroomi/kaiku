"""Description and review sources: loaders, typo pass, drafts, apply paths (fake Yext, no network)."""
import asyncio
import json
from datetime import date

import pytest

from kaiku import store
from kaiku.apply import yext as Y
from kaiku.chat import actions, feed as chat_feed
from kaiku.suggest import feed, sources as src

SAMPLE = ("Furry Paw Vet Clinic is a small animal clinic in Tikkurila, Vantaa. We treat dogs, cats and small pets and offer "
          "vacination, dental care, X-rays and day surgery. Appointments by phone or online. "
          "(Sample text written by team VY7 for the Since AI 2026 demo.)")


class FakeYext:
    def __init__(self, description=SAMPLE, reviews=None, can_comment=True):
        self.ent = {"name": "Furry Paw Vet Clinic", "address": {"line1": "Tikkurilantie 9", "city": "Vantaa"},
                    "categories": {"fonecta": ["E1700"]},
                    "hours": {"monday": {"openIntervals": [{"start": "09:00", "end": "17:00"}]},
                              "tuesday": {"openIntervals": [{"start": "09:00", "end": "17:00"}]}, "sunday": {"isClosed": True}}}
        if description is not None:
            self.ent["description"] = description
        self.reviews = json.loads(json.dumps(reviews or []))
        self.can_comment = can_comment
        self.puts = []

    def get_entity(self, eid):
        return json.loads(json.dumps(self.ent))

    def update_entity(self, eid, fields):
        self.puts.append(fields)
        self.ent.update(fields)
        return {}

    def list_reviews(self, eid):
        return json.loads(json.dumps(self.reviews))

    def post_review_comment(self, rid, content):
        if not self.can_comment:
            raise Y.YextError("HTTP 403: forbidden")
        for r in self.reviews:
            if str(r["id"]) == str(rid):
                r.setdefault("comments", []).append({"content": content})
        return {}


@pytest.fixture(autouse=True)
def _env(monkeypatch, tmp_path):
    monkeypatch.setenv("KAIKU_CHAT_NO_LLM", "1")
    monkeypatch.setenv("KAIKU_REPLIES_FILE", str(tmp_path / "replies.jsonl"))
    monkeypatch.setenv("KAIKU_DECLINES_FILE", str(tmp_path / "declines.jsonl"))
    src.clear_cache()


REV3 = {"id": 11, "rating": 3.0, "content": "Waited 40 minutes for a booked appointment. Staff were kind though.",
        "authorName": "Sample reviewer (fictional)", "comments": []}
REV5 = {"id": 12, "rating": 5.0, "content": "Kind staff, quick help for our cat.", "authorName": "Sample reviewer (fictional)", "comments": []}


# ---------- typos ----------
def test_deterministic_typo_vacination():
    t = src.deterministic_typos(SAMPLE)
    assert {"wrong": "vacination", "right": "vaccination"} in t
    assert "vaccination, dental care" in src.apply_typos(SAMPLE, t)
    assert src.deterministic_typos("Clean text. All fine here.") == []


def test_double_space_and_capital():
    t = src.deterministic_typos("we treat cats.  Open daily. then closed")
    fixed = src.apply_typos("we treat cats.  Open daily. then closed", t)
    assert fixed == "We treat cats. Open daily. Then closed"


def test_typo_card():
    cards = feed.description_loader("furry-paw", date(2026, 12, 1), FakeYext())
    assert len(cards) == 1
    c = cards[0]
    assert c["kind"] == "description" and c["title_en"] == "Typo in your description"
    assert c["text_en"] == '"vacination" should be "vaccination". Shall I fix it?'
    assert c["proposed"] == SAMPLE.replace("vacination", "vaccination") and c["confidence"] == 0.9
    assert c["holiday_date"] is None and c["status"] == "proposed"
    assert any(r["dataset_id"] == "urn:kaiku:src:yext:description" and r["source"] == "yext" for r in c["reasons"])
    assert any("sample description/reviews written by the team" in r["text_en"] for r in c["reasons"])


def test_no_typo_no_card():
    assert feed.description_loader("furry-paw", date(2026, 12, 1), FakeYext("A clean small clinic in Vantaa.")) == []


def test_description_missing_draft():
    c = feed.description_loader("furry-paw", date(2026, 12, 1), FakeYext(None))[0]
    assert c["title_en"] == "Your listing has no description"
    assert "Furry Paw Vet Clinic" in c["proposed"] and "Tikkurilantie 9" in c["proposed"]
    assert any(r["source"] == "kaiku_draft" and "draft by Kaiku" in r["text_en"] for r in c["reasons"])
    assert "Mon-Tue 9-17" in src.hours_summary(FakeYext().ent["hours"])


def test_llm_typos_validated(monkeypatch):
    monkeypatch.setattr(src, "_complete", lambda *a, **k: '{"typos":[{"wrong":"pets","right":"pets"},{"wrong":"nothere","right":"x"},{"wrong":"clinic","right":"klinic"}]}')
    got = src.llm_typos("A clinic.")
    assert got == [{"wrong": "clinic", "right": "klinic"}]
    monkeypatch.setattr(src, "_complete", lambda *a, **k: "not json")
    src.clear_cache()
    assert src.llm_typos("A clinic.") == []


# ---------- reviews ----------
def test_review_cards_low_rating_first_and_draft_fallback():
    cards = feed.review_loader("furry-paw", date(2026, 12, 1), FakeYext(reviews=[REV5, REV3]))
    assert [c["rating"] for c in cards] == [3, 5]
    c = cards[0]
    assert c["title_en"] == "A 3-star review has no reply" and c["confidence"] == 0.7
    assert c["text_en"].endswith("Here is a reply you could post:") and "Waited 40 minutes" in c["text_en"]
    assert 0 < len(c["proposed"].split()) <= 60 and "discount" not in c["proposed"].lower()
    assert c["holiday_date"] is None and c["review_id"] == "11"
    assert any(r["source"] == "yext_reviews" for r in c["reasons"])
    assert any("sample description/reviews written by the team" in r["text_en"] for r in c["reasons"])  # author is our sample


def test_review_fallback_file_when_sandbox_empty():
    cards = feed.review_loader("furry-paw", date(2026, 12, 1), FakeYext(reviews=[]))
    assert len(cards) == 2 and cards[0]["rating"] == 3
    assert cards[0]["reasons"][0]["source"] == "sample_reviews"
    assert any("written by the team" in r["text_en"] for r in cards[0]["reasons"])


def test_answered_review_has_no_card():
    assert feed.review_loader("furry-paw", date(2026, 12, 1), FakeYext(reviews=[{**REV3, "comments": [{"content": "hi"}]}])) == []


def test_reply_fi_fallback():
    assert "Kiitos" in src.reply_fallback(3, "x", "fi")
    assert len(src.reply_fallback(3, "x").split()) <= 60


# ---------- apply ----------
def test_apply_description_verified():
    c = FakeYext()
    out = Y.apply_description("SinceAI07", SAMPLE.replace("vacination", "vaccination"), c)
    assert out["yext_status"] == "ok" and out["verified"] and "vaccination" in c.ent["description"]


def test_apply_review_posts_or_stores(tmp_path):
    c = FakeYext(reviews=[REV3])
    out = Y.apply_review_reply("SinceAI07", "11", "Thank you for telling us.", c)
    assert out["posted"] and out["verified"] and not out["stored"]
    c2 = FakeYext(reviews=[REV3], can_comment=False)
    out2 = Y.apply_review_reply("SinceAI07", "11", "Thank you for telling us.", c2)
    assert not out2["posted"] and out2["stored"] and "403" in out2["post_error"]
    rows = [json.loads(l) for l in Y.reply_log_path().read_text().splitlines()]
    assert rows[0]["review_id"] == "11" and rows[0]["posted"] is False
    # a stored reply is not offered again
    assert feed.review_loader("furry-paw", date(2026, 12, 1), FakeYext(reviews=[REV3])) == []


# ---------- decide + with_decisions ----------
@pytest.fixture
def cards_feed(monkeypatch, tmp_path):
    fake = FakeYext(reviews=[REV3])
    items = feed.description_loader("furry-paw", date(2026, 12, 1), fake) + feed.review_loader("furry-paw", date(2026, 12, 1), fake)
    f = tmp_path / "feed.json"
    f.write_text(json.dumps({"business_id": "furry-paw", "suggestions": items}))
    monkeypatch.setenv("KAIKU_FEED_FIXTURE", str(f))
    monkeypatch.setenv("KAIKU_DATA_DIR", str(tmp_path))
    from kaiku.config import settings
    old = settings.DB_PATH
    store.reset(tmp_path / "s.sqlite")
    store.seed()
    yield fake, items
    store.reset(old)


def _by_kind(k):
    return next(i for i in chat_feed.get_feed("furry-paw")["suggestions"] if i["kind"] == k)


def test_decide_description_approve_then_status(cards_feed):
    fake, items = cards_feed
    d = _by_kind("description")
    r = asyncio.run(actions.decide("furry-paw", d["id"], "approve", _client=fake))
    assert r["ok"] and r["verified"] and r["yext"] == "ok"
    assert "vaccination" in fake.ent["description"] and "vacination" not in fake.ent["description"]
    assert store.get_suggestion(d["id"]).status == "applied"
    assert _by_kind("description")["status"] == "approved"
    evs = [e for e in store.recent_events(30) if e.suggestion_id == d["id"]]
    assert any(e.step == "apply" and e.title_en == "Description saved to Yext, read back and verified" for e in evs)
    assert asyncio.run(actions.decide("furry-paw", d["id"], "approve", _client=fake))["ok"] is False


def test_decide_description_edit_uses_owner_text(cards_feed):
    fake, _ = cards_feed
    d = _by_kind("description")
    r = asyncio.run(actions.decide("furry-paw", d["id"], "edit", edited_text="Family vet in Vantaa.", _client=fake))
    assert r["ok"] and fake.ent["description"] == "Family vet in Vantaa."
    assert asyncio.run(actions.decide("furry-paw", _by_kind("review")["id"], "edit", edited_text="  "))["ok"] is False


def test_decide_review_stored_honestly(cards_feed):
    fake, _ = cards_feed
    fake.can_comment = False
    rv = _by_kind("review")
    r = asyncio.run(actions.decide("furry-paw", rv["id"], "approve", _client=fake))
    assert r["ok"] and r["stored"] and not r["posted"]
    assert store.get_suggestion(rv["id"]).status == "approved"
    ev = next(e for e in store.recent_events(30) if e.suggestion_id == rv["id"] and e.step == "apply")
    assert ev.title_en == "Reply stored; the sandbox key cannot post review comments"
    assert _by_kind("review")["status"] == "approved"


def test_decide_review_posts_when_allowed(cards_feed):
    fake, _ = cards_feed
    rv = _by_kind("review")
    r = asyncio.run(actions.decide("furry-paw", rv["id"], "edit", edited_text="Thanks, we hear you.", _client=fake))
    assert r["posted"] and fake.reviews[0]["comments"][0]["content"] == "Thanks, we hear you."
    assert store.get_suggestion(rv["id"]).status == "applied"


def test_decline_learns(cards_feed):
    fake, _ = cards_feed
    d = _by_kind("description")
    r = asyncio.run(actions.decide("furry-paw", d["id"], "decline", _client=fake))
    assert r["ok"] and r["status"] == "declined" and not fake.puts
    assert _by_kind("description")["status"] == "declined"
    assert any(e.step == "learn" and e.suggestion_id == d["id"] for e in store.recent_events(30))


def test_with_decisions_does_not_touch_holiday_cards(cards_feed):
    fake, _ = cards_feed
    d = _by_kind("description")
    asyncio.run(actions.decide("furry-paw", d["id"], "decline", _client=fake))
    feedd = {"business_id": "furry-paw", "suggestions": [{"id": "h", "kind": "holiday_hours", "holiday_date": "2026-12-24", "status": "proposed"}]}
    assert chat_feed.with_decisions(feedd)["suggestions"][0]["status"] == "proposed"
