import asyncio

import pytest

from kaiku.contact import call as C
from kaiku.contact import call_router as CR
from kaiku.learn import prefs

from test_call import env, payload, run, tr  # noqa: F401


def test_prompts_have_closing_question():
    en, fi = C.agent_config("en"), C.agent_config("fi")
    assert "would you rather I message you on WhatsApp or email, or is a call fine?" in en["agent"]["prompt"]["prompt"]
    assert "WhatsApp it is, thanks!" in en["agent"]["prompt"]["prompt"]
    assert "WhatsAppilla tai sähköpostilla, vai sopiiko puhelu?" in fi["agent"]["prompt"]["prompt"]
    assert en["agent"]["first_message"] == C.FIRST_MESSAGE and fi["agent"]["first_message"] == C.FIRST_MESSAGE_FI
    assert "preferred_channel" in en["data_collection"] and "preferred_channel" in fi["data_collection"]
    assert "whatsapp | email | call" in en["data_collection"]["preferred_channel"]["description"]


def test_update_agent_keeps_env_voice(env, monkeypatch):
    monkeypatch.setenv("ELEVENLABS_AGENT_ID", "ag_9")
    monkeypatch.setenv("ELEVENLABS_VOICE_ID", "voiceX")

    class F:
        calls = []

        def __call__(self, m, u, h, p):
            self.calls.append((m, p))
            return 200, {"conversation_config": {"agent": {"language": "en", "first_message": C.FIRST_MESSAGE}}}
    f = F()
    C.update_agent(C.Api("k", f), "en")
    assert f.calls[0][1]["conversation_config"]["tts"]["voice_id"] == "voiceX"


def ana(ch, action="approve"):
    return {"data_collection_results": {"action": {"value": action}, "preferred_channel": {"value": ch}}}


@pytest.fixture
def pref_env(env, tmp_path, monkeypatch):
    monkeypatch.setattr(prefs, "data_dir", lambda: tmp_path, raising=False)
    seen = []
    monkeypatch.setattr(prefs, "_emit", lambda *a, **k: seen.append(a))
    return seen


def test_whatsapp_stored_and_event_emitted(pref_env):
    r = run(payload("c-1", analysis=ana("whatsapp")))
    assert r["decision"]["action"] == "approve"
    assert prefs.get_contact_channel("SinceAI07") == "whatsapp"
    assert len(pref_env) == 1


@pytest.mark.parametrize("val", ["none", "", "sms", None])
def test_none_stores_nothing(pref_env, val):
    r = run(payload("c-2", analysis=ana(val)))
    assert r["decision"]["action"] == "approve"
    assert prefs.get_contact_channel("SinceAI07") is None and pref_env == []


def test_call_and_email_stored(pref_env):
    run(payload("c-3", analysis=ana("email")))
    assert prefs.get_contact_channel("SinceAI07") == "email"
    run(payload("c-4", analysis=ana("call", "decline")))
    assert prefs.get_contact_channel("SinceAI07") == "call"


def test_closing_answer_not_read_as_decision():
    t = [{"role": "agent", "message": "Do you approve?"}, {"role": "user", "message": "yes"},
         {"role": "agent", "message": "Before I go, would you prefer WhatsApp or email, or is a call fine?"},
         {"role": "user", "message": "no, a call is fine"}]
    assert CR.parse_transcript(t) == {"action": "approve"}
