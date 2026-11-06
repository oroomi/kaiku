"""Browser tests for the live voice mode of client/pilot.js (Gemini Live over a WebSocket, OpenAI Realtime over WebRTC).
No network, no keys: /pilot/status, /pilot/live/session and /pilot/live/tools are fakes answered by the harness, and the page gets a fake
getUserMedia (a real oscillator stream), a fake WebSocket and a fake RTCPeerConnection that the test drives (window.__wsPush, window.__dcPush).
The page origin is not a secure context, so the mic goes through the ScriptProcessor path here; the AudioWorklet path has its own test below."""
from __future__ import annotations

import base64
import json

import pytest

from conftest import FAKE_SR, FAKE_SYNTH, ORIGIN, Harness

JSON_T = "application/json"
ZEROS_20MS = base64.b64encode(bytes(960)).decode()          # 480 samples of PCM16 silence at 24 kHz
ZEROS_LONG = base64.b64encode(bytes(48000 * 6)).decode()      # 6 s of samples: still playing when we interrupt it, even on a loaded box
GEMINI_URL = "wss://gemini.test/ws/BidiGenerateContentConstrained?access_token=tok"
GEMINI_SETUP = {"setup": {"model": "models/gemini-3.8-live", "generationConfig": {"responseModalities": ["AUDIO"]}}}
CALLS_URL = ORIGIN + "/fake-openai/calls"

FAKE_LIVE = """
window.__gum = 0; window.__micStreams = []; window.__micDenied = false;
(function () {
  var gum = function (c) {
    window.__gum += 1; window.__gumConstraints = c;
    if (window.__micDenied) return Promise.reject(new DOMException("denied", "NotAllowedError"));
    var ctx = new AudioContext(), osc = ctx.createOscillator(), dest = ctx.createMediaStreamDestination();
    osc.frequency.value = 220; osc.connect(dest); osc.start(); ctx.resume();
    window.__micStreams.push(dest.stream);
    return Promise.resolve(dest.stream);
  };
  if (!navigator.mediaDevices) Object.defineProperty(navigator, "mediaDevices", { value: {}, configurable: true });
  navigator.mediaDevices.getUserMedia = gum;
})();
window.__micEnded = function (i) { var s = window.__micStreams[i || 0]; return !!s && s.getTracks().every(function (t) { return t.readyState === "ended"; }); };   /* the first stream: the live session's */

window.__ws = null; window.__wsSent = []; window.__wsUrls = []; window.__wsClosed = false;
function FakeWS(url) {
  var self = this; window.__ws = this; window.__wsUrls.push(url); this.url = url; this.readyState = 0; window.__wsClosed = false;
  setTimeout(function () { self.readyState = 1; if (self.onopen) self.onopen({}); }, 0);
}
FakeWS.prototype.send = function (d) { window.__wsSent.push(JSON.parse(d)); };
FakeWS.prototype.close = function () { this.readyState = 3; window.__wsClosed = true; };
window.WebSocket = FakeWS;
window.__wsPush = function (obj, asBlob) { var d = JSON.stringify(obj); window.__ws.onmessage({ data: asBlob ? new Blob([d]) : d }); };

window.__pc = null; window.__dc = null; window.__dcSent = []; window.__pcClosed = false; window.__dcClosed = false; window.__pcs = 0;
function FakeDC() { this.readyState = "connecting"; window.__dc = this; }
FakeDC.prototype.send = function (d) { window.__dcSent.push(JSON.parse(d)); };
FakeDC.prototype.close = function () { this.readyState = "closed"; window.__dcClosed = true; };
function FakePC() { window.__pc = this; window.__pcs += 1; this.tracks = []; this.connectionState = "new"; window.__pcClosed = false; }
FakePC.prototype.addTrack = function (t) { this.tracks.push(t); return {}; };
FakePC.prototype.addTransceiver = function (kind, o) { window.__transceiver = [kind, o && o.direction]; return {}; };
FakePC.prototype.createDataChannel = function (label) { window.__dcLabel = label; this.dc = new FakeDC(); return this.dc; };
FakePC.prototype.createOffer = function () { return Promise.resolve({ type: "offer", sdp: "v=0 fake-offer" }); };
FakePC.prototype.setLocalDescription = function (d) { window.__localDesc = d; return Promise.resolve(); };
FakePC.prototype.setRemoteDescription = function (d) {
  var self = this; window.__remoteDesc = d;
  setTimeout(function () {                                     /* the model's voice arrives, then the data channel opens */
    var ctx = new AudioContext(), osc = ctx.createOscillator(), dest = ctx.createMediaStreamDestination();
    osc.connect(dest); osc.start(); ctx.resume();
    if (self.ontrack) self.ontrack({ streams: [dest.stream], track: dest.stream.getTracks()[0] });
    self.connectionState = "connected"; self.dc.readyState = "open"; if (self.dc.onopen) self.dc.onopen({});
  }, 0);
  return Promise.resolve();
};
FakePC.prototype.close = function () { this.connectionState = "closed"; window.__pcClosed = true; };
window.RTCPeerConnection = FakePC;
window.__dcPush = function (obj) { window.__dc.onmessage({ data: JSON.stringify(obj) }); };

window.__answers = [];
document.addEventListener("pilot:answer", function (e) { window.__answers.push(e.detail.text); });
"""

SCRIPTS = (FAKE_SR, FAKE_SYNTH, FAKE_LIVE)


class Rec:
    """What the fake live routes saw, and what /live/tools answers (by call id)."""

    def __init__(self):
        self.sessions: list = []
        self.tools: list = []
        self.script: dict = {}
        self.tools_status = 200


def navigate_and_highlight(rec, nav="c1", hi="c2"):
    rec.script[nav] = {"ok": True, "output": "Opened /matches.", "action": {"type": "navigate", "path": "/matches"}}
    rec.script[hi] = {"ok": True, "output": "Spotlight on match-1.", "action": {"type": "highlight", "target": "match-1", "caption": "Best match: 92"}}


def live_harness(harness, site, provider="gemini-live", session_status=200, scripts=SCRIPTS, extra=None):
    rec = Rec()
    status = {**site[0].get("/pilot/status").json(), "mode": "live", "brain": "test-brain", "voice": "test-voice"}
    status.pop("live", None)
    if provider:
        status["live"] = provider
    if provider == "gemini-live":
        info = {"provider": provider, "session": "sid-g", "model": "gemini-3.8-live", "url": GEMINI_URL, "setup": GEMINI_SETUP, "expires_at": "2026-10-21T20:00:00Z"}
    else:
        info = {"provider": "openai-realtime", "session": "sid-o", "model": "gpt-realtime-2.1", "token": "ek_test123", "calls_url": CALLS_URL, "expires_at": 1234}

    def session(body):
        rec.sessions.append(body)
        if session_status != 200:
            return session_status, JSON_T, json.dumps({"error": "nope"})
        return 200, JSON_T, json.dumps(info)

    def tools(body):
        rec.tools.append(body)
        if rec.tools_status != 200:
            return rec.tools_status, JSON_T, json.dumps({"error": "session expired"})
        results = [{"id": c["id"], "name": c["name"], **rec.script.get(c["id"], {"ok": False, "output": "unknown tool " + c["name"]})} for c in body["calls"]]
        return 200, JSON_T, json.dumps({"results": results})

    overrides = {"/pilot/status": lambda b: (200, JSON_T, json.dumps(status)), "/pilot/live/session": session, "/pilot/live/tools": tools}
    overrides.update(extra or {})
    h = harness(overrides=overrides, scripts=scripts)
    if provider == "openai-realtime":
        h.seen_calls = []

        def calls(route):
            req = route.request
            h.seen_calls.append({"method": req.method, "headers": req.headers, "body": req.post_data})
            route.fulfill(status=201, headers={"Content-Type": "application/sdp"}, body="v=0 fake-answer")
        h.page.route(CALLS_URL, calls)
    return h, rec


def wait_js(h, expr, timeout=5000):
    h.page.wait_for_function(expr, timeout=timeout)


def wait_state(h, state, timeout=5000):
    wait_js(h, f"window.VoicePilot.instance.state === '{state}'", timeout)


def frames(h):
    return h.page.evaluate("window.__wsSent")


def audio_frames(h):
    return [f["realtimeInput"]["audio"] for f in frames(h) if "realtimeInput" in f and "audio" in f["realtimeInput"]]


def open_gemini(h):
    page = h.goto("/")
    page.click(".vp-launch")
    wait_js(h, "window.__wsSent.length >= 1")
    page.evaluate("window.__wsPush({setupComplete: {}})")
    wait_state(h, "listening")
    return page


def open_openai(h):
    page = h.goto("/")
    page.click(".vp-launch")
    wait_js(h, "window.__dc && window.__dc.readyState === 'open'")
    wait_state(h, "listening")
    return page


# ---------------------------------------------------------------------------------------------------------------------------------
# Gemini Live
# ---------------------------------------------------------------------------------------------------------------------------------
def test_gemini_setup_first_then_mic_only_after_setup_complete(harness, site):
    h, rec = live_harness(harness, site)
    page = h.goto("/")
    assert page.text_content(".vp-badge") == "Live" and page.get_attribute(".vp-badge", "title") == "test-brain + test-voice"
    page.click(".vp-launch")
    wait_js(h, "window.__wsSent.length >= 1")
    assert page.evaluate("window.__wsUrls") == [GEMINI_URL]
    assert frames(h)[0] == GEMINI_SETUP, "the setup frame goes first, exactly as the server gave it"
    assert h.pilot("[p.state, p.elState.textContent]") == ["thinking", "Connecting"]
    assert rec.sessions[0]["manifest"]["page"]["path"] == "/" and not h.chats()
    page.wait_for_timeout(600)                                   # a mic callback fires every ~40 ms: none may reach the socket yet
    assert len(frames(h)) == 1 and page.evaluate("window.__gumConstraints") == {"audio": {"channelCount": 1, "echoCancellation": True, "noiseSuppression": True}}
    page.evaluate("window.__wsPush({setupComplete: {}})")
    wait_state(h, "listening")
    wait_js(h, "window.__wsSent.filter(f => f.realtimeInput && f.realtimeInput.audio).length >= 2")
    audio = audio_frames(h)
    assert all(a["mimeType"] == "audio/pcm;rate=16000" for a in audio)
    sizes = [len(base64.b64decode(a["data"])) for a in audio]
    assert all(s % 2 == 0 and s >= 3200 for s in sizes), sizes   # whole Int16 samples, at least 100 ms each
    assert page.evaluate("window.__srStarts") == 0, "no Web Speech in live mode"
    assert 0 <= h.pilot("p.live.micLevel()") <= 1 and not h.chats()


def test_gemini_tool_call_navigates_highlights_and_answers_in_one_batch(harness, site):
    h, rec = live_harness(harness, site)
    navigate_and_highlight(rec)
    rec.script["c3"] = {"ok": True, "output": "Opened the funders."}                       # a data tool: no action
    rec.script["c4"] = {"ok": False, "output": "no such tool"}
    rec.script["c5"] = {"ok": True, "output": "Spotlight on the ghost.", "action": {"type": "highlight", "target": "ghost", "caption": "x"}}
    page = open_gemini(h)
    page.evaluate("window.__marker = 'same page'")
    calls = [{"id": "c1", "name": "navigate", "args": {"path": "/matches"}}, {"id": "c2", "name": "highlight", "args": {"target": "match-1", "caption": "Best match: 92"}}]
    page.evaluate("(c) => window.__wsPush({toolCall: {functionCalls: c}}, true)", calls)       # a Blob, like the real socket sends
    wait_js(h, "window.__wsSent.some(f => f.toolResponse)")
    assert len(rec.tools) == 1, "navigate and highlight arrive together: ONE request"
    req = rec.tools[0]
    assert req["session"] == "sid-g" and req["calls"] == calls
    assert req["manifest"]["page"]["path"] == "/" and any(t["id"] == "hero" for t in req["manifest"]["targets"]) and len(req["manifest"]["pages"]) == 3
    assert page.evaluate("location.pathname") == "/matches" and page.evaluate("window.__marker") == "same page"
    assert h.pilot("p.mode") == "docked" and page.is_visible(".vp-orb") and page.is_visible(".vp-bubble")
    # the spotlight lands on match-1 (it glides there with a CSS transition, so wait until it has arrived)
    wait_js(h, "(() => { const s = document.querySelector('.vp-spot').getBoundingClientRect(), t = document.querySelector('[data-pilot=match-1]').getBoundingClientRect();"
               " return Math.max(Math.abs(s.left - t.left + 8), Math.abs(s.top - t.top + 8), Math.abs(s.width - t.width - 16), Math.abs(s.height - t.height - 16)) < 3; })()", 3000)
    assert page.is_visible(".vp-spot-label") and page.text_content(".vp-spot-label") == "Best match: 92"
    resp = [f for f in frames(h) if "toolResponse" in f]
    assert resp == [{"toolResponse": {"functionResponses": [
        {"id": "c1", "name": "navigate", "response": {"output": "Opened /matches."}},
        {"id": "c2", "name": "highlight", "response": {"output": "Spotlight on match-1."}}]}}]
    acts = h.pilot("p.log.filter(e => e.kind === 'action').map(e => [e.type, e.target || e.path, e.ok])")
    assert acts == [["navigate", "/matches", True], ["highlight", "match-1", True]]
    # a highlight the page cannot find: the model hears why. A data tool gives its output; a tool the server refused gives its error.
    page.evaluate("window.__wsPush({toolCall: {functionCalls: [{id: 'c5', name: 'highlight', args: {target: 'ghost'}}, {id: 'c3', name: 'list_funders', args: {}}, {id: 'c4', name: 'nope', args: {}}]}})")
    wait_js(h, "window.__wsSent.filter(f => f.toolResponse).length === 2")
    assert len(rec.tools) == 2 and rec.tools[1]["manifest"]["page"]["path"] == "/matches", "the manifest is the page as it is now"
    second = [f for f in frames(h) if "toolResponse" in f][1]["toolResponse"]["functionResponses"]
    assert {r["id"]: r["response"] for r in second} == {"c5": {"error": "not on this page"}, "c3": {"output": "Opened the funders."}, "c4": {"error": "no such tool"}}
    assert h.pilot("p.reports.length") == 0, "the model already heard the failure; nothing is queued for a /chat that never comes"
    assert not h.chats()


def test_gemini_audio_shows_speaking_and_text_barge_in_returns_to_listening(harness, site):
    h, rec = live_harness(harness, site)
    page = open_gemini(h)
    page.evaluate("window.__wsPush({serverContent: {inputTranscription: {text: 'show me'}}})")
    page.evaluate("window.__wsPush({serverContent: {inputTranscription: {text: ' the best match'}}})")
    wait_js(h, "document.querySelector('.vp-heard').textContent === 'show me the best match'")
    page.evaluate("(z) => window.__wsPush({serverContent: {modelTurn: {parts: [{inlineData: {data: z, mimeType: 'audio/pcm;rate=24000'}}]}, outputTranscription: {text: 'The best match '}}})", ZEROS_20MS)
    page.evaluate("window.__wsPush({serverContent: {outputTranscription: {text: 'is Kelpforge.'}}})")
    wait_state(h, "speaking")
    wait_js(h, "document.querySelector('.vp-say').textContent === 'The best match is Kelpforge.'")
    assert page.text_content(".vp-bubble-text") == "The best match is Kelpforge."
    assert 0 <= h.pilot("p.live.level()") <= 1
    page.evaluate("window.__wsPush({serverContent: {turnComplete: true}})")      # 20 ms of audio drains, then the mic is all there is again
    wait_state(h, "listening")
    assert page.evaluate("window.__answers") == ["The best match is Kelpforge."] and not page.evaluate("window.__wsClosed")
    # a new model turn starts a fresh text; speaking over it stops the audio at once
    page.evaluate("(z) => window.__wsPush({serverContent: {modelTurn: {parts: [{inlineData: {data: z}}]}, outputTranscription: {text: 'Second answer, a long one.'}}})", ZEROS_LONG)
    wait_state(h, "speaking")
    assert page.text_content(".vp-say") == "Second answer, a long one." and h.pilot("p.live.srcs.size") == 1
    page.evaluate("window.__wsPush({serverContent: {interrupted: true}})")
    wait_state(h, "listening")
    assert h.pilot("p.live.srcs.size") == 0
    page.evaluate("window.__wsPush({serverContent: {turnComplete: true}})")
    page.wait_for_timeout(100)
    assert h.pilot("p.state") == "listening" and page.evaluate("window.__wsClosed") is False
    assert len(page.evaluate("window.__answers")) == 2


def test_gemini_typed_question_goes_into_the_session(harness, site):
    h, rec = live_harness(harness, site)
    page = open_gemini(h)
    n = len(frames(h))
    page.click(".vp-link")                                       # "Type instead" keeps the session
    assert h.pilot("!!p.live") and page.is_visible(".vp-type input")
    page.fill(".vp-type input", "who should fund saltgrid")
    page.press(".vp-type input", "Enter")
    wait_js(h, f"window.__wsSent.slice({n}).some(f => f.realtimeInput && f.realtimeInput.text)")
    texts = [f["realtimeInput"]["text"] for f in frames(h) if "realtimeInput" in f and "text" in f["realtimeInput"]]
    assert texts == ["who should fund saltgrid"]
    assert page.text_content(".vp-heard") == "who should fund saltgrid" and not h.chats() and page.evaluate("window.__wsClosed") is False
    assert h.pilot("p.state") == "thinking"
    page.evaluate("(z) => window.__wsPush({serverContent: {modelTurn: {parts: [{inlineData: {data: z}}]}, outputTranscription: {text: 'Blue Current.'}, }})", ZEROS_20MS)
    wait_state(h, "speaking")


def test_gemini_ask_before_the_session_is_up_is_sent_once_it_is(harness, site):
    h, rec = live_harness(harness, site)
    page = h.goto("/")
    page.evaluate("window.VoicePilot.instance.open({ask: 'what is on the board?'})")
    wait_js(h, "window.__wsSent.length >= 1")
    page.wait_for_timeout(200)
    assert len(frames(h)) == 1 and frames(h)[0] == GEMINI_SETUP, "nothing but the setup before setupComplete"
    page.evaluate("window.__wsPush({setupComplete: {}})")
    wait_js(h, "window.__wsSent.some(f => f.realtimeInput && f.realtimeInput.text)")
    first_two = [f for f in frames(h) if "realtimeInput" not in f or "text" in f["realtimeInput"]]
    assert first_two == [GEMINI_SETUP, {"realtimeInput": {"text": "what is on the board?"}}] and not h.chats()


def test_gemini_cancelled_tool_calls_are_dropped_and_the_page_is_left_alone(harness, site):
    h, rec = live_harness(harness, site)
    navigate_and_highlight(rec)
    page = open_gemini(h)
    page.evaluate("window.__wsPush({toolCall: {functionCalls: [{id: 'c1', name: 'navigate', args: {path: '/matches'}}, {id: 'c2', name: 'highlight', args: {target: 'match-1'}}]}});"
                  "window.__wsPush({toolCallCancellation: {ids: ['c1', 'c2']}})")
    page.wait_for_timeout(800)
    assert page.evaluate("location.pathname") == "/" and not [f for f in frames(h) if "toolResponse" in f]


def test_gemini_session_ending_by_itself_goes_idle_with_a_message(harness, site):
    h, rec = live_harness(harness, site)
    page = open_gemini(h)
    page.evaluate("window.__wsPush({goAway: {timeLeft: '5s'}})")
    wait_state(h, "idle")
    assert h.pilot("p.elState.textContent") == "The live session ended. Tap the orb to start again."
    assert h.pilot("p.live") is None and page.evaluate("window.__wsClosed") and page.evaluate("window.__micEnded()")
    # the socket dropping, and the tools route saying the session is gone, end it the same way
    page.click(".vp-orb")
    wait_js(h, "window.__wsUrls.length === 2")
    page.evaluate("window.__wsPush({setupComplete: {}})")
    wait_state(h, "listening")
    page.evaluate("window.__ws.onclose({})")
    wait_state(h, "idle")
    page.click(".vp-orb")
    wait_js(h, "window.__wsUrls.length === 3")
    page.evaluate("window.__wsPush({setupComplete: {}})")
    wait_state(h, "listening")
    rec.tools_status = 403
    page.evaluate("window.__wsPush({toolCall: {functionCalls: [{id: 'c1', name: 'navigate', args: {path: '/matches'}}]}})")
    wait_state(h, "idle")
    assert "expired" in h.pilot("p.elState.textContent") and page.evaluate("location.pathname") == "/"
    assert h.pilot("p.live") is None and page.evaluate("window.__wsClosed")


def test_escape_ends_a_gemini_session_and_releases_the_mic(harness, site):
    h, rec = live_harness(harness, site)
    page = open_gemini(h)
    assert not page.evaluate("window.__wsClosed") and not page.evaluate("window.__micEnded()")
    page.keyboard.press("Escape")
    assert h.pilot("p.mode") == "closed" and h.pilot("p.live") is None
    assert page.evaluate("window.__wsClosed") is True and page.evaluate("window.__micEnded()") is True
    n = len(frames(h))
    page.wait_for_timeout(300)
    assert len(frames(h)) == n, "no audio frames after the session closed"


def test_tapping_the_orb_ends_the_live_session_and_tapping_again_starts_a_new_one(harness, site):
    h, rec = live_harness(harness, site)
    page = open_gemini(h)
    page.click(".vp-orb")
    assert h.pilot("[p.state, p.live, p.mode]") == ["idle", None, "full"] and page.evaluate("window.__wsClosed") and page.evaluate("window.__micEnded()")
    page.click(".vp-orb")
    wait_js(h, "window.__wsUrls.length === 2")
    assert h.pilot("p.state") == "thinking" and len(rec.sessions) == 2
    page.click(".vp-orb")                                        # even while connecting, a tap cancels
    assert h.pilot("[p.state, p.live]") == ["idle", None]
    page.click(".vp-orb")
    wait_js(h, "window.__wsUrls.length === 3")
    page.evaluate("window.__wsPush({setupComplete: {}})")
    wait_state(h, "listening")
    assert not page.evaluate("window.__wsClosed")


def test_without_a_microphone_the_session_still_runs_for_typed_questions(harness, site):
    h, rec = live_harness(harness, site)
    page = h.goto("/")
    page.evaluate("window.__micDenied = true")
    page.click(".vp-launch")
    wait_js(h, "window.__wsSent.length >= 1")
    page.evaluate("window.__wsPush({setupComplete: {}})")
    wait_state(h, "listening")
    assert h.pilot("p.elState.textContent") == "Type your question." and page.is_visible(".vp-type input")
    page.fill(".vp-type input", "hello")
    page.press(".vp-type input", "Enter")
    wait_js(h, "window.__wsSent.some(f => f.realtimeInput && f.realtimeInput.text === 'hello')")
    assert not audio_frames(h)


# ---------------------------------------------------------------------------------------------------------------------------------
# OpenAI Realtime
# ---------------------------------------------------------------------------------------------------------------------------------
def test_openai_offer_goes_to_calls_url_with_the_bearer_token(harness, site):
    h, rec = live_harness(harness, site, "openai-realtime")
    page = open_openai(h)
    assert len(h.seen_calls) == 1
    call = h.seen_calls[0]
    assert call["method"] == "POST" and call["body"] == "v=0 fake-offer"
    assert call["headers"]["authorization"] == "Bearer ek_test123" and call["headers"]["content-type"] == "application/sdp"
    assert page.evaluate("window.__remoteDesc") == {"type": "answer", "sdp": "v=0 fake-answer"}
    assert page.evaluate("window.__dcLabel") == "oai-events" and page.evaluate("window.__pc.tracks.length") == 1
    assert page.evaluate("window.__localDesc.type") == "offer"
    assert page.evaluate("(() => { const a = document.querySelector('audio[autoplay]'); return !!a && !!a.srcObject; })()"), "the model's voice plays in a hidden <audio>"
    assert rec.sessions[0]["manifest"]["page"]["path"] == "/" and not h.chats() and not page.evaluate("window.__srStarts")
    assert 0 <= h.pilot("p.live.micLevel()") <= 1 and 0 <= h.pilot("p.live.level()") <= 1


def test_openai_function_calls_make_one_request_two_outputs_and_one_response_create(harness, site):
    h, rec = live_harness(harness, site, "openai-realtime")
    navigate_and_highlight(rec, "call_1", "call_2")
    page = open_openai(h)
    page.evaluate("window.__dcPush({type: 'conversation.item.input_audio_transcription.completed', transcript: 'show me the best match '})")
    wait_js(h, "document.querySelector('.vp-heard').textContent === 'show me the best match'")
    page.evaluate("window.__dcPush({type: 'response.created', response: {}})")
    page.evaluate("window.__dcPush({type: 'response.output_audio_transcript.delta', delta: 'Let me '})")
    page.evaluate("window.__dcPush({type: 'response.output_audio_transcript.delta', delta: 'pull that up.'})")
    wait_state(h, "speaking")
    assert page.text_content(".vp-say") == "Let me pull that up."
    done = {"type": "response.done", "response": {"status": "completed", "output": [
        {"type": "message", "role": "assistant"},
        {"type": "function_call", "call_id": "call_1", "name": "navigate", "arguments": json.dumps({"path": "/matches"})},
        {"type": "function_call", "call_id": "call_2", "name": "highlight", "arguments": json.dumps({"target": "match-1", "caption": "Best match: 92"})}]}}
    page.evaluate("(d) => window.__dcPush(d)", done)
    wait_js(h, "window.__dcSent.some(f => f.type === 'response.create')")
    assert len(rec.tools) == 1 and rec.tools[0]["session"] == "sid-o"
    assert rec.tools[0]["calls"] == [{"id": "call_1", "name": "navigate", "args": {"path": "/matches"}}, {"id": "call_2", "name": "highlight", "args": {"target": "match-1", "caption": "Best match: 92"}}]
    assert rec.tools[0]["manifest"]["page"]["path"] == "/" and len(rec.tools[0]["manifest"]["pages"]) == 3
    sent = page.evaluate("window.__dcSent")
    assert [f["type"] for f in sent] == ["conversation.item.create", "conversation.item.create", "response.create"], sent
    assert [(f["item"]["type"], f["item"]["call_id"], f["item"]["output"]) for f in sent[:2]] == [
        ("function_call_output", "call_1", "Opened /matches."), ("function_call_output", "call_2", "Spotlight on match-1.")]
    assert page.evaluate("location.pathname") == "/matches" and h.pilot("p.mode") == "docked"
    assert page.text_content(".vp-spot-label") == "Best match: 92"
    # a failing highlight is reported to the model as an error string
    rec.script["call_3"] = {"ok": True, "output": "Spotlight on the ghost.", "action": {"type": "highlight", "target": "ghost"}}
    page.evaluate("window.__dcSent.length = 0")
    page.evaluate("window.__dcPush({type: 'response.done', response: {output: [{type: 'function_call', call_id: 'call_3', name: 'highlight', arguments: '{\"target\": \"ghost\"}'}]}})")
    wait_js(h, "window.__dcSent.some(f => f.type === 'response.create')")
    sent = page.evaluate("window.__dcSent")
    assert [f["type"] for f in sent] == ["conversation.item.create", "response.create"] and sent[0]["item"]["output"] == "ERROR: not on this page"
    # the answer after the tools: its words follow the lead-in, the turn ends when the audio does
    page.evaluate("window.__dcPush({type: 'response.created'})")
    page.evaluate("window.__dcPush({type: 'response.output_audio_transcript.delta', delta: 'The best match is Kelpforge.'})")
    page.evaluate("window.__dcPush({type: 'output_audio_buffer.started'})")
    page.evaluate("window.__dcPush({type: 'response.done', response: {output: [{type: 'message'}]}})")
    page.wait_for_timeout(150)
    assert h.pilot("p.state") == "speaking", "response.done is not the end of the audio"
    page.evaluate("window.__dcPush({type: 'output_audio_buffer.stopped'})")
    wait_state(h, "listening")
    assert page.evaluate("window.__answers") == ["Let me pull that up. The best match is Kelpforge."], "the turn is the lead-in and the answer after the tools"
    assert [f["type"] for f in page.evaluate("window.__dcSent")] == ["conversation.item.create", "response.create"], "no stray sends"


def test_openai_barge_in_and_the_short_timeout_when_there_are_no_audio_buffer_events(harness, site):
    h, rec = live_harness(harness, site, "openai-realtime")
    page = open_openai(h)
    page.evaluate("window.__dcPush({type: 'response.output_audio_transcript.delta', delta: 'A long answer that gets cut off.'})")
    wait_state(h, "speaking")
    page.evaluate("window.__dcPush({type: 'input_audio_buffer.speech_started'})")
    wait_state(h, "listening")
    page.evaluate("window.__dcPush({type: 'response.output_audio_transcript.delta', delta: 'Short.'})")
    wait_state(h, "speaking")
    assert page.text_content(".vp-say") == "Short.", "a new turn starts a new text"
    page.evaluate("window.__dcPush({type: 'response.done', response: {output: [{type: 'message'}]}})")
    page.wait_for_timeout(300)
    assert h.pilot("p.state") == "speaking"
    wait_state(h, "listening", 4000)                             # ~1.2 s later
    assert page.evaluate("window.__answers")[-1] == "Short."
    page.evaluate("window.__dcPush({type: 'error', error: {message: 'Rate limit hit.'}})")
    assert page.text_content(".vp-say") == "Rate limit hit." and h.pilot("p.log.some(e => e.kind === 'live-error' && e.message === 'Rate limit hit.')")


def test_openai_typed_question_and_close(harness, site):
    h, rec = live_harness(harness, site, "openai-realtime")
    page = open_openai(h)
    page.click(".vp-link")
    page.fill(".vp-type input", "who should fund saltgrid")
    page.press(".vp-type input", "Enter")
    wait_js(h, "window.__dcSent.some(f => f.type === 'response.create')")
    assert page.evaluate("window.__dcSent") == [
        {"type": "conversation.item.create", "item": {"type": "message", "role": "user", "content": [{"type": "input_text", "text": "who should fund saltgrid"}]}},
        {"type": "response.create"}]
    assert not h.chats() and page.text_content(".vp-heard") == "who should fund saltgrid"
    assert not page.evaluate("window.__pcClosed") and not page.evaluate("window.__micEnded()")
    page.keyboard.press("Escape")
    assert h.pilot("[p.mode, p.live]") == ["closed", None]
    assert page.evaluate("window.__pcClosed") is True and page.evaluate("window.__dcClosed") is True and page.evaluate("window.__micEnded()") is True
    assert page.evaluate("document.querySelector('audio[autoplay]')") is None, "the hidden <audio> is removed"


def test_openai_connection_failure_before_the_channel_opens_falls_back_to_classic(harness, site):
    h, rec = live_harness(harness, site, "openai-realtime")
    page = h.goto("/")
    page.route(CALLS_URL, lambda route: route.fulfill(status=401, body="bad token"))
    page.click(".vp-launch")
    page.wait_for_function("window.__sr && window.VoicePilot.instance.state === 'listening'", timeout=5000)
    assert h.pilot("p.liveBroken") is True and page.evaluate("window.__pcClosed") and page.evaluate("window.__micEnded()")
    assert h.pilot("p.log.some(e => e.kind === 'live-fallback' && e.why.includes('401'))")


# ---------------------------------------------------------------------------------------------------------------------------------
# Falling back, and not being used at all
# ---------------------------------------------------------------------------------------------------------------------------------
@pytest.mark.parametrize("code", [503, 404, 409, 429, 502])
def test_a_failing_live_session_route_falls_back_to_web_speech_and_chat(harness, site, code):
    chat = sse_chat("Classic answer.")
    h, rec = live_harness(harness, site, session_status=code, extra={"/pilot/chat": lambda b: (200, "text/event-stream", chat)})
    page = h.goto("/")
    page.click(".vp-launch")
    page.wait_for_function("window.__sr && window.VoicePilot.instance.state === 'listening'", timeout=5000)
    assert len(rec.sessions) == 1 and page.evaluate("window.__srStarts") == 1 and not page.evaluate("window.__wsUrls.length")
    assert h.pilot(f"p.log.some(e => e.kind === 'live-fallback' && e.why === 'live session {code}')")
    assert h.pilot("p.liveBroken") is True and h.pilot("p.live") is None and page.evaluate("window.__micEnded()")
    page.evaluate("window.__say([['show me the best match', true]])")
    page.click(".vp-orb")                                        # tap-to-send, the classic way
    wait_state(h, "done", 8000)
    assert len(h.chats()) == 1 and h.chats()[0]["messages"][-1]["content"] == "show me the best match"
    assert page.evaluate("window.__spoken") == ["Classic answer."]
    # the failure is remembered: the next listen goes straight to Web Speech
    page.click(".vp-orb")
    wait_state(h, "listening")
    assert len(rec.sessions) == 1 and page.evaluate("window.__srStarts") == 2


def test_a_question_asked_while_live_fails_to_start_is_answered_the_classic_way(harness, site):
    chat = sse_chat("It is the Kelpforge page.")
    h, rec = live_harness(harness, site, session_status=503, extra={"/pilot/chat": lambda b: (200, "text/event-stream", chat)})
    page = h.goto("/")
    page.evaluate("window.VoicePilot.instance.open({ask: 'what is Kelpforge?'})")
    wait_state(h, "done", 8000)
    assert len(rec.sessions) == 1 and len(h.chats()) == 1 and h.chats()[0]["messages"][-1]["content"] == "what is Kelpforge?"
    assert page.evaluate("window.__spoken") == ["It is the Kelpforge page."]
    page.evaluate("window.VoicePilot.instance.ask('and the next step?')")
    page.wait_for_function("window.__spoken.length >= 2", timeout=8000)
    assert len(rec.sessions) == 1 and len(h.chats()) == 2


def test_no_live_key_or_live_off_or_no_browser_support_means_the_classic_path(harness, site):
    # 1. /status without "live"
    h, rec = live_harness(harness, site, provider=None)
    page = h.goto("/")
    assert not page.is_visible(".vp-badge") or page.text_content(".vp-badge") != "Live"
    page.click(".vp-launch")
    page.wait_for_function("window.__sr && window.VoicePilot.instance.state === 'listening'")
    assert not rec.sessions and not page.evaluate("window.__wsUrls.length") and not page.evaluate("window.__pcs")
    # 2. option live: "off" even though the server offers it
    h2, rec2 = live_harness(harness, site, scripts=SCRIPTS + ("window.PILOT_TEST_OPTS = {live: 'off'};",))
    page2 = h2.goto("/")
    page2.click(".vp-launch")
    page2.wait_for_function("window.__sr && window.VoicePilot.instance.state === 'listening'")
    assert not rec2.sessions and h2.pilot("p.liveBroken") is False
    # 3. a browser without RTCPeerConnection cannot do openai-realtime
    h3, rec3 = live_harness(harness, site, "openai-realtime", scripts=SCRIPTS + ("delete window.RTCPeerConnection;",))
    page3 = h3.goto("/")
    page3.click(".vp-launch")
    page3.wait_for_function("window.__sr && window.VoicePilot.instance.state === 'listening'")
    assert not rec3.sessions and h3.pilot("p.liveBroken") is False


def sse_chat(text):
    from conftest import sse
    return sse(("delta", {"text": text, "step": 1}), ("done", {"text": text}))


# ---------------------------------------------------------------------------------------------------------------------------------
# The real mic path: AudioWorklet needs a secure context, so this page is http://localhost (the fake origin above is not secure)
# ---------------------------------------------------------------------------------------------------------------------------------
LOCAL = "http://localhost:8199"


class LocalHarness(Harness):
    def __init__(self, browser, site, overrides, scripts):
        super().__init__(browser, site, {"width": 1280, "height": 800}, overrides, scripts)
        self.page.route(LOCAL + "/**", self._local)

    def _local(self, route):
        req = route.request
        path = req.url[len(LOCAL):] or "/"
        body = req.post_data_buffer
        self.requests.append({"method": req.method, "path": path, "body": body})
        for prefix, fn in self.overrides.items():
            if path.startswith(prefix):
                status, ctype, out = fn(json.loads(body) if body else None)
                return route.fulfill(status=status, headers={"Content-Type": ctype}, body=out)
        r = self.client.request(req.method, path, content=body, headers={"Content-Type": req.headers.get("content-type", "application/json"), "Accept": req.headers.get("accept", "*/*")})
        headers = {k: v for k, v in r.headers.items() if k.lower() not in ("content-length", "content-encoding", "transfer-encoding")}
        route.fulfill(status=r.status_code, headers=headers, body=r.content)


def test_the_audio_worklet_path_streams_real_samples_on_a_secure_page(browser, site):
    status = {**site[0].get("/pilot/status").json(), "mode": "live", "live": "gemini-live"}
    info = {"provider": "gemini-live", "session": "sid-g", "url": GEMINI_URL, "setup": GEMINI_SETUP}
    h = LocalHarness(browser, site, {"/pilot/status": lambda b: (200, JSON_T, json.dumps(status)), "/pilot/live/session": lambda b: (200, JSON_T, json.dumps(info))}, SCRIPTS)
    try:
        page = h.page
        page.goto(LOCAL + "/")
        page.wait_for_function("window.VoicePilot && window.VoicePilot.instance && window.VoicePilot.instance.status")
        assert page.evaluate("window.isSecureContext && !!AudioContext.prototype && 'audioWorklet' in AudioContext.prototype")
        page.click(".vp-launch")
        page.wait_for_function("window.__wsSent.length >= 1")
        page.evaluate("window.__wsPush({setupComplete: {}})")
        page.wait_for_function("window.VoicePilot.instance.state === 'listening'")
        page.wait_for_function("window.__wsSent.filter(f => f.realtimeInput && f.realtimeInput.audio).length >= 3", timeout=8000)
        assert page.evaluate("window.VoicePilot.instance.live.node.constructor.name") == "AudioWorkletNode"
        audio = [f["realtimeInput"]["audio"] for f in page.evaluate("window.__wsSent") if "realtimeInput" in f]
        pcm = b"".join(base64.b64decode(a["data"]) for a in audio)
        samples = [int.from_bytes(pcm[i:i + 2], "little", signed=True) for i in range(0, len(pcm) - 1, 2)]
        assert all(a["mimeType"] == "audio/pcm;rate=16000" for a in audio) and len(samples) >= 4800
        assert max(abs(s) for s in samples) > 1000, "the 220 Hz oscillator comes through as real samples, not silence"
        page.keyboard.press("Escape")
        assert page.evaluate("window.__wsClosed") is True
    finally:
        h.close()
