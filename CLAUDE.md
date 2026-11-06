# Kaiku, Since AI 2026 (Fonecta challenge "Connect suggests, customer approves") + Aura (FIWARE entry)

Team: Dayo (solo on site, pitches, phone, Q&A) + Claude (Fable orchestrates, sonnet builders in worktrees, sonnet verifiers).
Event: Fri 6 Nov 15:00 to Sun 8 Nov. SUBMISSION CLOSES SUN 8 NOV 10:00 EET (hard). Fonecta Q&A at Joki Sat 09:00-12:00: a
working prototype must be demoable on a phone + laptop by Sat 09:00. Feature freeze Sat 22:00. Submit Sun 09:00.

## What we are building (read FONECTA brief: /root/hack/dossiers/sinceai-2026/BRIEFING_PACK_FRI.md section 2)
Fonecta Connect publishes a business's opening hours to Google, Apple, Bing, directories and AI services. Today the customer
must log in and remember to add holiday hours; they forget; customers turn up at a closed door. The challenge: a working demo
of the WHOLE CHAIN for holiday hours, all five steps, "a complete chain beats a perfect single step":
1 DETECT (what data says the hours need to change) 2 SUGGEST (which hours, and why exactly those) 3 CONTACT (reach the
customer, explain why; NO login) 4 DECIDE (one tap: approve / edit / no thanks; the customer always has the last word)
5 APPLY (write to OUR Yext sandbox entity, tell the customer where it shows). Plus: LEARN (next suggestion better after an edit
or decline; standing permission for recurring changes), RELIABILITY (how wrong suggestions are prevented: confidence gate,
ask instead of guess), EXTENSIBILITY (same loop for review replies / posts), COLD START (customer with no history).
Fonecta scores suggestion quality with a SCORING SCRIPT on HIDDEN TEST DATA (dataset not released yet; design the suggest
engine with a pluggable dataset loader and machine-readable output).
Contact ladder (Dayo's decision): WhatsApp first, then a phone call by Kaiku (ElevenLabs voice, Finnish). NO EMAIL.
Demo business: the Yext sandbox entity "Furry Paw Vet Clinic", Vantaa (fictional, provisioned by Fonecta; id SinceAI07).
Hero holiday: jouluaatto Thu 24 Dec 2026 reached by TIME TRAVEL (fake "today"). Isanpaiva Sun 8 Nov is NOT a public holiday
(flag day): for a vet closed on Sundays the right answer is "no change", shown as reliability, not silence.
FIWARE: the NGSI-LD context broker (Orion-LD) is the chain's SPINE and must be visible: Detect = subscription fires, Suggest =
proposed attribute instance (datasetId urn:kaiku:src:proposed), Decide = owner's tap writes the default instance, Apply =
notification writes Yext. Each source is its own instance of the same attribute (datasetId per source, observedAt).
The Yext write NEVER depends on the broker being up: broker/fallback.py keeps the chain alive and events say "broker offline".

## Non-negotiables
- Every line of product code is written during the event (bell commit e2f7382). Pre-existing, declared in DISCLOSURE.md:
  our MIT library github.com/oroomi/voice-pilot (vendored under vendor/voice-pilot, licence kept), /root/hack/bin process
  scripts, public datasets/APIs, the Yext sandbox, our VPS + Cloudflare tunnel. Nothing else from earlier projects. Do NOT copy
  code from /root/hack/kompassi, /root/hack/jx2026, /root/hack/kits/sinceai-templates or any mock html; read them only as words.
- No fabricated data shown as real. Fictional data is LABELLED ("sample", "fictional"). Real OSM/Föli/AIS data is cited.
  Every number on screen comes from a data call. Missing data shows "no data".
- No persons: businesses only. The owner's phone number in demos = Dayo's own.
- Secrets only in /root/hack/kaiku/.env (chmod 600, gitignored). Never print secret values. Never touch any other secrets
  file on the box. If a key is missing, mark BLOCKED in your report and build against a fake.
- Finnish copy: correct Finnish, no em dashes anywhere (use commas or full stops), dates "24.12.", times "9-13".
- Never `pkill -f`/`killall`. Stop servers by port (`fuser -k PORT/tcp`) or systemd unit. Commit every 20-30 min.

## Stack and layout (fixed; do not rename)
FastAPI + Jinja2 + vanilla JS (no build step), SQLite app state, Orion-LD + MongoDB in Docker (compose in broker/), MapLibre
for maps, voice-pilot (vendored) for Kaiku's voice. Python 3.12, `pip install -r requirements.txt` into /root/hack/kaiku/.venv.
Main app port 8210 (systemd unit hack-kaiku via /root/hack/bin/deploy.sh). Orion-LD on 127.0.0.1:1026. Builders test on
their own port 82xx given in their task. 
Public URL: https://kaiku.hankintaviikko.fi
```
kaiku/            app.py config.py events.py store.py chain.py (CORE, owner: core builder)
kaiku/broker/     client.py models.py subs.py fallback.py router.py docker-compose.yml   (owner: broker)
kaiku/detect/     holidays.py signals.py engine.py                                        (owner: detect-suggest)
kaiku/suggest/    engine.py explain.py schema.py cli.py backtest.py                       (owner: detect-suggest)
kaiku/contact/    whatsapp.py call.py ladder.py messages.py router.py                     (owner: whatsapp / call)
kaiku/decide/     tokens.py router.py                                                     (owner: decide)
kaiku/apply/      yext.py publishers.py                                                   (owner: apply-yext)
kaiku/learn/      prefs.py timetravel.py                                                  (owner: learn)
kaiku/voice/      tools.py manifest.json                                                  (owner: voice)
kaiku/web/templates/  base.html + <module>_*.html     kaiku/web/static/ horizon.css app.js map.js   (base+css: core)
ngsi-ld-mcp/      standalone MCP server package (FIWARE entry; also used by kaiku/voice)  (owner: mcp)
aura/             feed adapters + map page (FIWARE entry "Aura", after Kaiku is green)    (owner: aura)
data/             seeds: furry_paw.json (fictional, labelled), holidays_fi_2026.json, osm_turku.json
tests/            test_<module>.py per owner      docs/<module>.md per owner
```
Router contract: every module exposes `router = APIRouter()` in `kaiku/<module>/router.py`; `kaiku/app.py` includes each
inside try/except ImportError, so a module can land without editing app.py. Templates extend `base.html` and use the blocks
`title`, `content`, `scripts`. Each page root carries `data-pilot` targets (ids) for Kaiku's spotlight.

## Data contracts (kaiku/schema.py, owned by core; others import, never redefine)
Business {id, name, address, city, lat, lon, category, regular_hours: {mon..sun: [{start:"09:00",end:"17:00"}] | []},
  last_year_exceptions: [{date:"2025-12-24", hours:[{start,end}] | "closed"}], website, owner_whatsapp, source}
Holiday {date, name_fi, name_en, public_holiday: bool, weekday}
Detection {business_id, holiday_date, signals: {regular_that_day, last_year, website, google_now, peers}, reason_codes}
Suggestion {id, business_id, holiday_date, kind: hours|closed|no_change|ask, proposed: [{start,end}] | null,
  confidence: 0..1, reasons: [{source, dataset_id, text_fi, text_en}], message_fi, message_en,
  status: proposed|sent|approved|edited|declined|applied|expired, channel_log: [{channel, at, detail}]}
Decision {suggestion_id, action: approve|edit|decline, edited: [{start,end}]|"closed"|null, reason_chip, standing_permission,
  via: whatsapp|call|web|voice, at}
ApplyResult {suggestion_id, yext_status, publishers: [str], broker_updated: bool, at}
Event {ts, step: detect|suggest|contact|decide|apply|learn|broker, business_id, suggestion_id, title_fi, title_en, detail}
Events: `kaiku.events.emit(Event)` persists to SQLite and pushes to SSE `/api/events` (core). Every step emits.
Time: `kaiku.learn.timetravel.today()` is THE clock for the chain (fake date via `/api/timetravel?date=2026-12-17`).

## The loop (every task)
1. Read this file and your task block in TASKS.md. Write the check first (test or exact URL + what must be visible).
2. Build the smallest thing that passes. Work ONLY in your owned paths. Commit on your task branch every 20-30 min.
3. Run `pytest -q tests/test_<module>.py`; for pages run `/root/hack/bin/shot.py <url> --name <task>` and READ both PNGs.
4. Write docs/<module>.md (what it does, data sources, what didn't work) and update DISCLOSURE.md if you used a new service.
5. End with `RESULT: <one sentence a judge could repeat> | tests: N passed | blocked: <none|what>`.
Verifiers (hack-verify) try to break every task on the running URL; FAIL = back to the builder.

## Design (locked by Dayo 6 Nov: the HORIZON look; spec in /root/hack/dossiers/sinceai-2026/KAIKU_DESIGN_SPEC.md)
Teal-to-night stage (#2f6f8c > #163746 > #0c1418 > #090b0d), two soft cyan glows (#8fd3e8, blur 70px), glass panels
rgba(255,255,255,.08/.12) edge .18, Newsreader 300 for the one plain sentence, Inter for UI, IBM Plex Mono small caps labels,
arc hero with a sweeping dot. Colours mean one thing each: red #ff8a7a wrong, green #9fe0b5 true/approved, cyan Kaiku points
here, warn #ffd27a missing. Phone width first (390), every screen screenshotted at 1440 and 390. Fonts vendored locally (OFL).
No purple gradients, no emoji headings, no "Welcome to", no placeholder avatars, no lorem ipsum.
