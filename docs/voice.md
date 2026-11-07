# voice (task 9): Kaiku on every page
Hold space or the orb, speak, release. EN glosses in brackets.

**Architecture.** `base.html` includes `_voice.html` (orb, mute, caption strip) + `voice.js/css`. Browser: MediaRecorder (webm/opus, mp4 on Safari) ->
`POST /api/voice/stt` -> `POST /api/voice/ask` -> `POST /api/voice/tts` -> `<audio>` (unlocked on the first press for iOS). The browser never sees a key.
Page change: if an action navigates elsewhere, the answer and remaining actions wait in sessionStorage and the next page speaks and spotlights them.

**Routes.** `/api/voice/stt` raw audio body, scribe_v1, 400 if empty/under 800 bytes, 413 over 6 MB. `/api/voice/tts` `{text}` -> audio/mpeg, eleven_v4,
cached by sha256(voice|model|format|text) in `data/tts_cache/` (self-ignoring), daily char cap `VOICE_TTS_DAILY_CHARS`. `/api/voice/ask` `{text,page,lang,history}` -> `{text, actions, tools, steps, ms}`.

**Brain.** `brain.py`: Anthropic `claude-sonnet-5-5`, manual tool loop, max 6 steps, effort low. Actions are built server-side from the tools that ran (the model never writes
selectors): `navigate {url}`, `spotlight {selector}` (only `[data-pilot=...]`), `run_chain {...}`. Page targets: hero (the suggestion), business-card, event-strip, today.
**Tools** (`tools.py`): get_business, get_suggestions (read-only preview when none stored), get_events, run_chain, timetravel, get_today; broker tools list_entities,
get_entity, propose_update through the ngsi-ld-mcp `Gateway` (guarded import, `NGSI_LD_MCP_HIDE_DECISIONS=1`; approve/reject are never exposed).

**The four lines (real API, 6 Nov).** "Kaiku, what's wrong with Furry Paw?" -> Christmas Eve 24.12. shows 9-17, last year 9-13, suggests 9-13; spotlight on hero.
"Mitä ehdotat jouluaatoksi?" [What do you suggest for Christmas Eve?] -> "Ehdotan jouluaatolle 24.12. aukioloajaksi 9-13 ...". "Run the chain for Christmas Eve" ->
run_chain(furry-paw, 2026-12-24), "The chain is running ...", event strip spotlighted. "Travel to the second of November" -> timetravel(2026-11-02), says it detects Father's Day 8.11.,
not a public holiday, closed Sundays, so no change.

**Latency (this VPS).** TTS 0.26-0.36 s uncached, 0 ms cached. STT 1.0-1.3 s for a 3 s line. Ask 3.4-6.1 s (one tool round, two model calls); first spoken audio about 4-7 s after release.

**Kit vs ours.** From `vendor/voice-pilot` (MIT, pre-existing, see VENDORED.md): the design (data-pilot targets, spotlight, push to talk, captions, ElevenLabs proxy + cache) and the
reference code; not loaded at runtime. Written here: every file under `kaiku/voice/`, `voice.js`, `voice.css`, `_voice.html`, the tools, Kaiku prompts, tests.

**Notes.** There is no separate business page, so navigate goes to `/` (the business card and hero live there). `anthropic` is in requirements.txt. `KAIKU_LIVE_VOICE=1` runs live tests.
