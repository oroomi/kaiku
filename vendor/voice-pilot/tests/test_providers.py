"""The provider layer: every brain runs the same tool loop against a fake of its own wire format (server/providers/fakes.py), the live voices mint
their credentials against a fake transport, and rehearsal mode works with every PILOT_BRAIN. No network and no keys: the "keys" below are
placeholders that only ever reach in-process fakes."""
from __future__ import annotations

import json
import re

import httpx
import pytest
from fastapi import FastAPI
from fastapi.testclient import TestClient

from server import config
from server.fake import FakeClient, reply, text, tool
from server.providers import chat_brain
from server.providers.base import iter_sse
from server.providers.fakes import HTTPReply
from server.providers.openai import _ThinkFilter
from server.registry import Registry, clean_manifest
from server.router import make_router
from server.turn import Turn

MANIFEST = {
    "app": {"name": "Sample app", "description": "A test app."},
    "page": {"path": "/", "title": "Home"},
    "targets": [{"id": "hero", "desc": "The hero"}, {"id": "apply", "desc": "Apply button", "safe": True}],
    "pages": [{"path": "/", "title": "Home", "targets": []},
              {"path": "/matches", "title": "Matches", "targets": [{"id": "match-1", "desc": "Top match"}]},
              {"path": "/startups/:slug", "title": "Startup", "targets": [{"id": "why", "desc": "Why it fits"}]}],
}
HTTP_BRAINS = ["gemini", "openai", "local"]
ALL_BRAINS = ["anthropic", "gemini", "gemini-live", "openai", "openai-realtime", "local"]
PLACEHOLDER = "test-placeholder-not-a-key"


@pytest.fixture(autouse=True)
def clean_env(monkeypatch):
    for k in ("PILOT_BRAIN", "PILOT_VOICE", "PILOT_REHEARSAL", "ANTHROPIC_API_KEY", "GEMINI_API_KEY", "GOOGLE_API_KEY", "OPENAI_API_KEY",
              "NVIDIA_API_KEY", "PILOT_LOCAL_API_KEY", "PILOT_LOCAL_BASE_URL", "ELEVENLABS_API_KEY", "ELEVENLABS_VOICE_ID"):
        monkeypatch.delenv(k, raising=False)


def _events(turn):
    return [(e["event"], e["data"]) for e in turn.events()]


def _turn(kind, script, reg=None, **kw):
    brain = chat_brain(kind)
    client = brain.fake_client(script)
    t = Turn([{"role": "user", "content": "show me the best match"}], clean_manifest(MANIFEST), reg or Registry(), client, config.settings(),
             brain=brain, **kw)
    return t, client


def _no_key(obj, key="additionalProperties"):
    if isinstance(obj, dict):
        return key not in obj and all(_no_key(v, key) for v in obj.values())
    if isinstance(obj, list):
        return all(_no_key(v, key) for v in obj)
    return True


# ---- the same loop on every HTTP brain --------------------------------------------------------------------------------------------------
@pytest.mark.parametrize("kind", HTTP_BRAINS)
def test_every_brain_runs_data_tools_then_ui_tools_then_streams_the_answer_with_cues(kind):
    reg = Registry()
    seen = {}

    @reg.tool("list_matches", "matches", {"type": "object", "properties": {"limit": {"type": "integer"}}}, label="reading the list")
    def list_matches(args):
        seen["args"] = args
        return {"top": "Kelpforge"}

    script = [reply(tool("list_matches", limit=3)),
              reply(tool("navigate", path="/matches"), tool("highlight", target="match-1", caption="Best match"), tool("highlight", target="nope")),
              reply(text("[[1]] Here are the matches. [[2]] Kelpforge is the best one.", chunks=["[[1]] Here are the mat", "ches. [[2]] Kelp",
                                                                                                 "forge is the best one."]))]
    turn, client = _turn(kind, script, reg)
    ev = _events(turn)
    assert [k for k, _ in ev][0] == "status" and ev[-1][0] == "done", ev
    assert ("status", {"label": "reading the list", "tool": "list_matches"}) in ev
    acts = [d for k, d in ev if k == "action"]
    assert [(a["id"], a["type"]) for a in acts] == [(1, "navigate"), (2, "highlight")]
    said = "".join(d["text"] for k, d in ev if k == "delta")
    assert said == "[[1]] Here are the matches. [[2]] Kelpforge is the best one." == ev[-1][1]["text"]
    assert seen["args"] == {"limit": 3}
    done = ev[-1][1]
    assert done["steps"] == 3 and len(done["actions"]) == 2 and done["usage"]["output_tokens"] == 120
    assert done["model"] == chat_brain(kind).model(config.settings())
    from server.providers.fakes import view
    r2 = view(kind, client.calls[1]["body"])["messages"][-1]["content"]
    assert r2[0]["type"] == "tool_result" and "Kelpforge" in r2[0]["content"] and not r2[0].get("is_error")
    r3 = view(kind, client.calls[2]["body"])["messages"][-1]["content"]
    assert "[[1]]" in r3[0]["content"] and "[[2]]" in r3[1]["content"]
    assert r3[2]["is_error"] and "Unknown target 'nope'" in r3[2]["content"]


@pytest.mark.parametrize("kind", HTTP_BRAINS)
def test_every_brain_forbids_tools_on_the_last_step_and_maps_errors(kind, monkeypatch):
    monkeypatch.setenv("PILOT_MAX_STEPS", "2")
    turn, client = _turn(kind, [reply(tool("wait", ms=200)), reply(text("Done waiting."))])
    ev = _events(turn)
    assert ev[-1][0] == "done"
    from server.providers.fakes import view
    assert not view(kind, client.calls[0]["body"])["final"] and view(kind, client.calls[1]["body"])["final"]
    for status, want in [(401, "auth"), (429, "busy"), (500, "api")]:
        turn, _ = _turn(kind, [HTTPReply(status, '{"error": "x"}')])
        assert _events(turn)[-1] == ("error", {"kind": want, "message": {"auth": "Aava's model key was refused.",
                                                                          "busy": "Aava is busy right now. Try again in a moment.",
                                                                          "api": "Aava's reasoning is not available right now."}[want]})
    turn, _ = _turn(kind, [httpx.ConnectError("refused")])
    assert _events(turn)[-1][1]["kind"] == "network"
    turn, _ = _turn(kind, [httpx.ReadTimeout("slow")])
    assert _events(turn)[-1][1]["kind"] == "timeout"
    turn, _ = _turn(kind, [reply(stop="refusal")])
    assert _events(turn)[-1] == ("error", {"kind": "refusal", "message": "Aava can't help with that one."})
    turn, _ = _turn(kind, [reply(text("  "))])
    assert _events(turn)[-1][1]["kind"] == "empty"


# ---- Gemini ------------------------------------------------------------------------------------------------------------------------------
def test_gemini_request_shape_thought_signatures_and_function_responses(monkeypatch):
    monkeypatch.setenv("GEMINI_API_KEY", PLACEHOLDER)
    turn, client = _turn("gemini", [reply(text("One moment."), tool("highlight", target="hero"), tool("click", target="hero")),
                                    reply(text("[[1]] That is the hero."))])
    ev = _events(turn)
    assert "".join(d["text"] for k, d in ev if k == "delta") == "One moment. [[1]] That is the hero."
    c0, c1 = client.calls
    assert c0["url"] == "https://generativelanguage.googleapis.com/v1beta/models/gemini-3.8-flash:streamGenerateContent?alt=sse"
    assert c0["headers"]["x-goog-api-key"] == PLACEHOLDER
    b0, b1 = c0["body"], c1["body"]
    decl = {d["name"]: d for d in b0["tools"][0]["functionDeclarations"]}
    assert {"navigate", "scroll_to", "highlight", "click", "fill", "wait"} <= set(decl) and _no_key(b0["tools"])
    assert decl["highlight"]["parameters"]["required"] == ["target"]
    assert "PAGE MAP" in b0["systemInstruction"]["parts"][0]["text"] and "match-1" in b0["systemInstruction"]["parts"][0]["text"]
    assert b0["toolConfig"] == {"functionCallingConfig": {"mode": "AUTO"}}
    assert b0["generationConfig"] == {"maxOutputTokens": 4096, "thinkingConfig": {"thinkingLevel": "low"}}
    assert b0["contents"] == [{"role": "user", "parts": [{"text": "show me the best match"}]}]
    model_turn, results = b1["contents"][-2], b1["contents"][-1]
    assert model_turn["role"] == "model" and [p["thoughtSignature"] for p in model_turn["parts"] if "functionCall" in p] == \
        [f"sig-{p['functionCall']['id']}" for p in model_turn["parts"] if "functionCall" in p]          # passed back exactly as received
    fr = [p["functionResponse"] for p in results["parts"]]
    assert [f["name"] for f in fr] == ["highlight", "click"] and "output" in fr[0]["response"] and "error" in fr[1]["response"]
    assert fr[0]["id"] == model_turn["parts"][1]["functionCall"]["id"]


def test_gemini_retries_once_without_thinking_and_handles_calls_without_ids(monkeypatch):
    turn, client = _turn("gemini", [HTTPReply(400, '{"error": {"message": "thinking_level is not supported for this model"}}'), reply(text("Hi."))])
    assert _events(turn)[-1][0] == "done"
    assert "thinkingConfig" in client.calls[0]["body"]["generationConfig"] and "thinkingConfig" not in client.calls[1]["body"]["generationConfig"]
    sent = []

    def handler(req):
        body = json.loads(req.content)
        sent.append(body)
        if len(sent) == 1:
            chunk = {"candidates": [{"content": {"role": "model", "parts": [{"functionCall": {"name": "highlight", "args": {"target": "hero"}}}]},
                                     "finishReason": "STOP"}]}
        else:
            chunk = {"candidates": [{"content": {"role": "model", "parts": [{"text": "[[1]] Here."}]}, "finishReason": "STOP"}]}
        return httpx.Response(200, headers={"content-type": "text/event-stream"}, content=f"data: {json.dumps(chunk)}\r\n\r\n".encode())
    brain = chat_brain("gemini")
    t = Turn([{"role": "user", "content": "x"}], clean_manifest(MANIFEST), Registry(), httpx.Client(transport=httpx.MockTransport(handler)),
             config.settings(), brain=brain)
    ev = _events(t)
    assert ev[-1][0] == "done" and [d["type"] for k, d in ev if k == "action"] == ["highlight"]
    assert sent[1]["contents"][-1]["parts"][0]["functionResponse"].keys() == {"name", "response"}     # no id was sent, so none comes back


# ---- OpenAI Responses -------------------------------------------------------------------------------------------------------------------
def test_openai_responses_request_shape_and_items_passed_back(monkeypatch):
    monkeypatch.setenv("OPENAI_API_KEY", PLACEHOLDER)
    turn, client = _turn("openai", [reply(tool("highlight", target="hero"), tool("click", target="hero")), reply(text("[[1]] The hero."))])
    assert _events(turn)[-1][0] == "done"
    c0, c1 = client.calls
    assert c0["url"] == "https://api.openai.com/v1/responses" and c0["headers"]["authorization"] == f"Bearer {PLACEHOLDER}"
    b0, b1 = c0["body"], c1["body"]
    assert b0["model"] == "gpt-6.1-sol" and b0["stream"] is True and b0["store"] is False and b0["tool_choice"] == "auto"
    assert b0["reasoning"] == {"effort": "low"} and b0["include"] == ["reasoning.encrypted_content"]
    hl = next(t for t in b0["tools"] if t["name"] == "highlight")
    assert hl["type"] == "function" and hl["strict"] is False and hl["parameters"]["properties"]["target"]["type"] == "string"
    assert "PAGE MAP" in b0["instructions"] and b0["input"] == [{"role": "user", "content": "show me the best match"}]
    calls = [i for i in b1["input"] if i.get("type") == "function_call"]
    outs = [i for i in b1["input"] if i.get("type") == "function_call_output"]
    assert [c["name"] for c in calls] == ["highlight", "click"] and [o["call_id"] for o in outs] == [c["call_id"] for c in calls]
    assert "[[1]]" in outs[0]["output"] and outs[1]["output"].startswith("ERROR: ") and "not marked safe" in outs[1]["output"]


def test_openai_retries_once_without_reasoning_parameters():
    turn, client = _turn("openai", [HTTPReply(400, '{"error": {"message": "Unsupported parameter: reasoning.effort"}}'), reply(text("Hi."))])
    assert _events(turn)[-1][0] == "done"
    assert "reasoning" in client.calls[0]["body"] and "reasoning" not in client.calls[1]["body"] and "include" not in client.calls[1]["body"]


# ---- OpenAI-compatible Chat Completions (NVIDIA NIM / Nemotron, vLLM) ------------------------------------------------------------------
def test_local_endpoint_request_shape_key_and_base_url(monkeypatch):
    monkeypatch.setenv("PILOT_LOCAL_BASE_URL", "http://127.0.0.1:8000/v1")
    turn, client = _turn("local", [reply(tool("highlight", target="hero")), reply(text("[[1]] Here."))])
    assert _events(turn)[-1][0] == "done"
    c0, c1 = client.calls
    assert c0["url"] == "http://127.0.0.1:8000/v1/chat/completions" and "authorization" not in c0["headers"]
    b0 = c0["body"]
    assert b0["model"] == "nvidia/nemotron-3.5-lightning-30b-a3b" and b0["messages"][0]["role"] == "system" and "PAGE MAP" in b0["messages"][0]["content"]
    assert b0["tools"][0]["type"] == "function" and b0["tools"][0]["function"]["name"] == "navigate" and b0["tool_choice"] == "auto"
    assert b0["stream_options"] == {"include_usage": True}
    asst, res = c1["body"]["messages"][-2], c1["body"]["messages"][-1]
    assert asst["role"] == "assistant" and json.loads(asst["tool_calls"][0]["function"]["arguments"]) == {"target": "hero"}   # split pieces joined
    assert res["role"] == "tool" and res["tool_call_id"] == asst["tool_calls"][0]["id"]
    monkeypatch.delenv("PILOT_LOCAL_BASE_URL")
    monkeypatch.setenv("NVIDIA_API_KEY", PLACEHOLDER)                                  # a key alone means build.nvidia.com's hosted NIM
    turn, client = _turn("local", [reply(text("Hi."))])
    _events(turn)
    assert client.calls[0]["url"] == "https://integrate.api.nvidia.com/v1/chat/completions"
    assert client.calls[0]["headers"]["authorization"] == f"Bearer {PLACEHOLDER}"


def test_local_endpoint_drops_think_blocks_and_retries_without_stream_options(monkeypatch):
    monkeypatch.setenv("PILOT_MAX_STEPS", "1")
    turn, client = _turn("local", [reply(text("x", chunks=["<thi", "nk>the plan</thi", "nk>Hel", "lo there."]))])
    ev = _events(turn)
    assert "".join(d["text"] for k, d in ev if k == "delta") == "Hello there." and "tools" not in client.calls[0]["body"]
    turn, client = _turn("local", [HTTPReply(400, "stream_options is not supported"), reply(text("Hi."))])
    assert _events(turn)[-1][0] == "done" and "stream_options" not in client.calls[1]["body"]
    f = _ThinkFilter()
    assert f.feed("a<think>b") + f.feed("c</think>d<") + f.feed("e") + f.flush() == "ad<e"
    assert list(iter_sse(["event: x", "data: {\"a\": 1}", "", ": comment", "data: [DONE]", ""])) == [("x", '{"a": 1}'), ("message", "[DONE]")]


# ---- the HTTP routes: status, rehearsal with every brain, the live voices --------------------------------------------------------------
def _demo():
    from server.app import app, pilot
    pilot.pilot.limiter.reset()
    return TestClient(app), pilot.pilot


DEMO_MANIFEST = {"page": {"path": "/", "title": "Home"}, "targets": [{"id": "hero"}],
                 "pages": [{"path": "/matches", "targets": [{"id": "match-1"}]}, {"path": "/startups/:slug", "targets": [{"id": "why"}, {"id": "next-step"}]}]}


def _sse(body: str) -> list[tuple[str, dict]]:
    out = []
    for block in body.strip().split("\n\n"):
        lines = dict(line.split(": ", 1) for line in block.split("\n") if ": " in line)
        out.append((lines["event"], json.loads(lines["data"])))
    return out


@pytest.mark.parametrize("brain", ALL_BRAINS)
def test_rehearsal_mode_runs_the_same_tour_with_every_brain(brain, monkeypatch):
    monkeypatch.setenv("PILOT_REHEARSAL", "1")
    monkeypatch.setenv("PILOT_BRAIN", brain)
    c, st = _demo()
    s = c.get("/pilot/status").json()
    assert s["mode"] == "rehearsal" and s.get("live") is None and (brain == "anthropic" or s["brain"] == brain)
    r = c.post("/pilot/chat", json={"messages": [{"role": "user", "content": "show me the best match and why"}], "manifest": DEMO_MANIFEST})
    ev = _sse(r.text)
    acts = [d for k, d in ev if k == "action"]
    assert [a["type"] for a in acts] == ["navigate", "highlight", "navigate", "highlight", "highlight"]
    said = ev[-1][1]["text"]
    assert ev[-1][0] == "done" and said.startswith("[[1]] [[2]] The best match is Kelpforge") and "[[5]] Next step:" in said
    assert c.post("/pilot/live/session", json={"manifest": DEMO_MANIFEST}).status_code in (404, 409)   # rehearsal keeps the classic voice path


def test_status_names_the_brain_only_when_configured_and_the_no_key_message_names_its_key(monkeypatch):
    c, st = _demo()
    assert set(c.get("/pilot/status").json()) == {"name", "mode", "llm", "model", "tts", "tts_chars_left"}      # the default answer is unchanged
    monkeypatch.setenv("PILOT_BRAIN", "gemini")
    s = c.get("/pilot/status").json()
    assert s["mode"] == "off" and s["brain"] == "gemini" and s["voice"] == "elevenlabs" and s["live"] is None
    r = c.post("/pilot/chat", json={"messages": [{"role": "user", "content": "hi"}], "manifest": MANIFEST})
    assert "GEMINI_API_KEY" in _sse(r.text)[0][1]["message"]
    monkeypatch.setenv("GEMINI_API_KEY", PLACEHOLDER)
    s = c.get("/pilot/status").json()
    assert s["mode"] == "live" and s["model"] == "gemini-3.8-flash" and s["live"] is None
    monkeypatch.setenv("PILOT_BRAIN", "gemini-live")
    assert c.get("/pilot/status").json()["live"] == "gemini-live"
    monkeypatch.setenv("PILOT_VOICE", "openai-realtime")                  # a live voice of another family is refused, with a warning
    assert c.get("/pilot/status").json()["voice"] == "elevenlabs"
    monkeypatch.setenv("PILOT_BRAIN", "nonsense")
    assert config.settings().brain == "anthropic"
    for k, v in (("PILOT_BRAIN", "anthropic"), ("PILOT_VOICE", "browser"), ("ELEVENLABS_API_KEY", PLACEHOLDER), ("ELEVENLABS_VOICE_ID", "v1")):
        monkeypatch.setenv(k, v)
    s = c.get("/pilot/status").json()
    assert s["tts"] is False and s["voice"] == "browser" and c.post("/pilot/tts", json={"text": "Hello"}).status_code == 404


def test_the_anthropic_request_is_the_same_whether_pilot_brain_is_unset_or_anthropic(monkeypatch):
    def run():
        client = FakeClient([reply(tool("highlight", target="hero")), reply(text("[[1]] Hi."))])
        ev = _events(Turn([{"role": "user", "content": "x"}], clean_manifest(MANIFEST), Registry(), client, config.settings()))
        return re.sub(r"toolu_fake_\d+", "toolu_N", repr(client.calls)), [e for e in ev if e[0] != "done"]
    a = run()
    monkeypatch.setenv("PILOT_BRAIN", "anthropic")
    assert run() == a


class MintFake(httpx.Client):
    def __init__(self, answer: dict, status: int = 200):
        self.calls = []

        def handle(req):
            self.calls.append({"url": str(req.url), "headers": dict(req.headers), "body": json.loads(req.content)})
            return httpx.Response(status, json=answer)
        super().__init__(transport=httpx.MockTransport(handle))

    def close(self):
        return None


def _live_app(monkeypatch, brain, answer, status=200, key_var="GEMINI_API_KEY"):
    monkeypatch.setenv("PILOT_BRAIN", brain)
    monkeypatch.setenv(key_var, PLACEHOLDER)
    reg = Registry()

    @reg.tool("list_matches", "matches", {"type": "object", "properties": {}, "additionalProperties": False}, label="reading the list")
    def list_matches(args):
        return {"top": "Kelpforge"}
    app = FastAPI()
    router = make_router(reg, app_name="Test app")
    app.include_router(router)
    fake = MintFake(answer, status)
    router.pilot.live_http = lambda s: fake
    return TestClient(app), router.pilot, fake


def test_gemini_live_session_mints_a_locked_token_and_never_returns_the_key(monkeypatch):
    c, st, fake = _live_app(monkeypatch, "gemini-live", {"name": "auth_tokens/abc123"})
    r = c.post("/pilot/live/session", json={"manifest": MANIFEST})
    assert r.status_code == 200, r.text
    d = r.json()
    assert PLACEHOLDER not in r.text and d["provider"] == "gemini-live" and d["model"] == "gemini-3.8-live" and len(d["session"]) >= 20
    assert d["url"] == ("wss://generativelanguage.googleapis.com/ws/google.ai.generativelanguage.v1beta.GenerativeService."
                        "BidiGenerateContentConstrained?access_token=auth_tokens%2Fabc123")
    setup = d["setup"]["setup"]
    assert setup["model"] == "models/gemini-3.8-live" and setup["generationConfig"]["responseModalities"] == ["AUDIO"]
    assert setup["inputAudioTranscription"] == {} and setup["outputAudioTranscription"] == {}
    names = [f["name"] for f in setup["tools"][0]["functionDeclarations"]]
    assert {"navigate", "highlight", "list_matches"} <= set(names) and _no_key(setup["tools"])
    sysx = setup["systemInstruction"]["parts"][0]["text"]
    assert "PAGE MAP" in sysx and "match-1" in sysx and "call the tool first" in sysx and "[[" not in sysx
    call = fake.calls[0]
    assert call["url"] == "https://generativelanguage.googleapis.com/v1beta/auth_tokens" and call["headers"]["x-goog-api-key"] == PLACEHOLDER
    b = call["body"]
    assert b["uses"] == 1 and b["expireTime"].endswith("Z") and b["newSessionExpireTime"].endswith("Z")
    lc = b["liveConnectConstraints"]
    assert lc["model"] == "models/gemini-3.8-live" and lc["config"]["systemInstruction"] == setup["systemInstruction"]
    assert lc["config"]["tools"] == setup["tools"] and lc["config"]["responseModalities"] == ["AUDIO"]


def test_live_tool_calls_are_validated_like_chat_and_data_tools_run_on_the_server(monkeypatch):
    c, st, _ = _live_app(monkeypatch, "gemini-live", {"name": "auth_tokens/abc123"})
    sid = c.post("/pilot/live/session", json={"manifest": MANIFEST}).json()["session"]
    calls = [{"id": "a", "name": "navigate", "args": {"path": "/startups/kelpforge"}}, {"id": "b", "name": "highlight", "args": {"target": "why"}},
             {"id": "c", "name": "highlight", "args": {"target": "match-1"}}, {"id": "d", "name": "list_matches", "args": {}},
             {"id": "e", "name": "rm_rf", "args": {}}, {"id": "f", "name": "click", "args": {"target": "hero"}}]
    r = c.post("/pilot/live/tools", json={"session": sid, "calls": calls, "manifest": MANIFEST})
    res = r.json()["results"]
    assert [(x["id"], x["ok"]) for x in res] == [("a", True), ("b", True), ("c", False), ("d", True), ("e", False), ("f", False)]
    assert res[0]["action"] == {"type": "navigate", "path": "/startups/kelpforge", "id": 1} and "Targets there: why" in res[0]["output"]
    assert res[1]["action"]["target"] == "why" and "Unknown target 'match-1'" in res[2]["output"] and res[2]["action"] is None
    assert "Kelpforge" in res[3]["output"] and res[3]["action"] is None and "no tool called" in res[4]["output"]
    assert "Unknown target 'hero' on /startups/kelpforge" in res[5]["output"]          # the tour moved: hero is on the page it left
    assert c.post("/pilot/live/tools", json={"session": "made-up", "calls": calls, "manifest": MANIFEST}).status_code == 403
    assert c.post("/pilot/live/tools", json={"session": sid, "calls": [], "manifest": MANIFEST}).status_code == 400
    monkeypatch.setenv("PILOT_LIVE_MAX_CALLS", "8")
    assert c.post("/pilot/live/tools", json={"session": sid, "calls": calls, "manifest": MANIFEST}).status_code == 403   # 6 used, 6 more > 8


def test_live_session_refusals(monkeypatch):
    c, st, fake = _live_app(monkeypatch, "gemini-live", {"error": {"message": "API key not valid"}}, status=400)
    r = c.post("/pilot/live/session", json={"manifest": MANIFEST})
    assert r.status_code == 502 and PLACEHOLDER not in r.text and "API key" not in r.text
    monkeypatch.delenv("GEMINI_API_KEY")
    assert c.post("/pilot/live/session", json={"manifest": MANIFEST}).status_code == 503
    monkeypatch.setenv("PILOT_BRAIN", "gemini")
    assert c.post("/pilot/live/session", json={"manifest": MANIFEST}).status_code == 404               # no live voice configured
    monkeypatch.setenv("PILOT_BRAIN", "gemini-live")
    monkeypatch.setenv("GEMINI_API_KEY", PLACEHOLDER)
    monkeypatch.setenv("PILOT_RATE_PER_MIN", "1")
    st.live_http = lambda s: MintFake({"name": "auth_tokens/x"})
    st.limiter.reset()
    assert [c.post("/pilot/live/session", json={"manifest": MANIFEST}).status_code for _ in range(2)] == [200, 429]


def test_openai_realtime_session_mints_a_client_secret_with_the_whole_session(monkeypatch):
    c, st, fake = _live_app(monkeypatch, "openai-realtime", {"value": "ek_test123", "expires_at": 1893456000, "session": {}}, key_var="OPENAI_API_KEY")
    assert c.get("/pilot/status").json()["live"] == "openai-realtime"
    r = c.post("/pilot/live/session", json={"manifest": MANIFEST})
    d = r.json()
    assert r.status_code == 200 and PLACEHOLDER not in r.text
    assert d == {"provider": "openai-realtime", "model": "gpt-realtime-2.1", "token": "ek_test123", "expires_at": 1893456000,
                 "calls_url": "https://api.openai.com/v1/realtime/calls", "session": d["session"]}
    call = fake.calls[0]
    assert call["url"] == "https://api.openai.com/v1/realtime/client_secrets" and call["headers"]["authorization"] == f"Bearer {PLACEHOLDER}"
    b = call["body"]
    assert b["expires_after"] == {"anchor": "created_at", "seconds": 120}
    sess = b["session"]
    assert sess["type"] == "realtime" and sess["model"] == "gpt-realtime-2.1" and sess["audio"]["output"]["voice"] == "marin"
    assert sess["audio"]["input"]["transcription"] == {"model": "gpt-live-transcribe"} and sess["tool_choice"] == "auto"
    assert {t["name"] for t in sess["tools"]} >= {"navigate", "highlight", "list_matches"} and all(t["type"] == "function" for t in sess["tools"])
    assert "PAGE MAP" in sess["instructions"] and "hero" in sess["instructions"]


def test_the_example_drives_the_same_page_with_two_brains(monkeypatch):
    import runpy
    monkeypatch.setenv("PILOT_BRAIN", "anthropic")          # the example sets these two; monkeypatch puts the old values back afterwards
    monkeypatch.setenv("PILOT_REHEARSAL", "1")
    ex = runpy.run_path(str(__import__("pathlib").Path(__file__).resolve().parent.parent / "examples" / "two_providers.py"), run_name="example")
    a, b = ex["run"]("anthropic", False), ex["run"]("openai", False)
    assert a["mode"] == b["mode"] == "rehearsal" and a["actions"] == b["actions"] and len(a["actions"]) == 5 and a["said"] == b["said"]


def test_review_fixes_no_arg_tools_nvidia_key_scope_and_the_daily_live_cap(monkeypatch):
    from server.providers.gemini import declarations
    from server.providers.openai import local_key
    d = {x["name"]: x for x in declarations([{"name": "ping", "description": "no args", "input_schema": {"type": "object", "properties": {}}},
                                            {"name": "wait", "description": "", "input_schema": {"type": "object", "properties": {"ms": {"type": "integer"}}}}])}
    assert "parameters" not in d["ping"] and d["wait"]["parameters"]["properties"] == {"ms": {"type": "integer"}}
    monkeypatch.setenv("NVIDIA_API_KEY", PLACEHOLDER)
    assert local_key("https://integrate.api.nvidia.com/v1") == PLACEHOLDER and local_key("http://evil.example/v1") == ""
    assert local_key("http://nvidia.com.evil.example/v1") == ""
    monkeypatch.setenv("PILOT_LOCAL_API_KEY", "other-placeholder")
    assert local_key("http://127.0.0.1:8000/v1") == "other-placeholder"
    c, st, fake = _live_app(monkeypatch, "gemini-live", {"name": "auth_tokens/x"})
    monkeypatch.setenv("PILOT_LIVE_DAILY_SESSIONS", "2")
    assert [c.post("/pilot/live/session", json={"manifest": MANIFEST}).status_code for _ in range(3)] == [200, 200, 429]
