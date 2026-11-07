"""A chain-run suggestion and its chat feed card are the same thing to WhatsApp and to the chain."""
import asyncio
import json

from kaiku import chain, store
from kaiku.contact import router as R
from kaiku.schema import Suggestion


def _chain_sug(sid="chain1", day="2026-12-24"):
    return Suggestion.model_validate({"id": sid, "business_id": "furry-paw", "holiday_date": day, "kind": "hours",
                                      "proposed": [{"start": "09:00", "end": "13:00"}], "confidence": 0.75, "reasons": [],
                                      "message_fi": "", "message_en": "", "status": "sent", "channel_log": []})


def test_feed_id_for_maps_a_chain_run_to_the_holiday_card(tmp_path, monkeypatch):
    f = tmp_path / "feed.json"
    f.write_text(json.dumps({"suggestions": [{"id": "feed-furry-paw-holiday_hours-2026-12-24", "kind": "holiday_hours",
                                               "title_en": "Christmas Eve 24.12.", "text_en": "x", "proposed": [{"start": "09:00", "end": "13:00"}],
                                               "confidence": 0.75, "status": "proposed", "holiday_date": "2026-12-24", "reasons": []}]}))
    monkeypatch.setenv("KAIKU_FEED_FIXTURE", str(f))
    store.save_suggestion(_chain_sug())
    assert R.feed_id_for("furry-paw", "chain1") == "feed-furry-paw-holiday_hours-2026-12-24"
    assert R.feed_id_for("furry-paw", "feed-furry-paw-holiday_hours-2026-12-24") == "feed-furry-paw-holiday_hours-2026-12-24"
    assert R.feed_id_for("furry-paw", "nope") is None
    assert R._business_for("chain1") == "furry-paw"


def test_on_decision_resolves_the_waiting_run_by_holiday_date():
    store.save_suggestion(_chain_sug("chain2"))
    loop = asyncio.new_event_loop()
    fut = loop.create_future()
    chain._waiters["chain2"] = fut
    try:
        ok = loop.run_until_complete(chain.on_decision({"suggestion_id": "feed-furry-paw-holiday_hours-2026-12-24", "action": "approve", "via": "whatsapp"}))
        assert ok is True and fut.done() and fut.result().suggestion_id == "chain2" and fut.result().action == "approve"
        assert "chain2" not in chain._waiters
    finally:
        chain._waiters.pop("chain2", None)
        loop.close()
