# Core (app, schema, store, events, chain, Horizon home)

## Run
```
python3 -m venv .venv && .venv/bin/pip install -r requirements.txt
.venv/bin/uvicorn kaiku.app:app --host 127.0.0.1 --port 8210      # or your own 82xx port
.venv/bin/pytest -q tests/test_core.py
```
Deployed as systemd unit `hack-kaiku` (port 8210) via `/root/hack/bin/deploy.sh`; public at https://kaiku.hankintaviikko.fi.
Settings come from `.env` through `kaiku/config.py` (`settings.PORT, DB_PATH, BROKER_URL, PUBLIC_URL, OWNER_WHATSAPP`). Values are never printed.
Static css/js are served `no-cache` and pages append `?v=<mtime>` so the Cloudflare edge never serves a stale copy.
The Playwright browsers under /root/.cache/ms-playwright match the system python3, not the venv: run shot.py/smoke.py with system python.

## Endpoints
| Method, path | What |
|---|---|
| GET `/` | Horizon home (arc hero, live strip, business card, run button) |
| GET `/healthz` | `{ok: true, broker: "unknown"}` (broker module may take over the field) |
| POST `/api/run?business=furry-paw&date=2026-12-24` | starts the chain in the background, returns `{suggestion_id}` at once. Core assigns the id and overrides whatever `suggest` returned |
| GET `/api/suggestions?business=&limit=` , `/api/suggestions/{id}` | Suggestion JSON (404 until the suggest step has finished) |
| GET `/api/business/{id}` | Business JSON |
| GET `/api/today` | `{date, label_fi, label_en}`; delegates to `kaiku.learn.timetravel.today()` when that module exists, else pref `today` (default 2026-12-17) |
| GET `/api/events?replay=1&last=50` | Server-Sent Events, `event: kaiku`, `data:` = Event JSON, `: keepalive` comment every 15 s |
| GET `/api/events/recent?limit=50&business=` | JSON list, oldest first |
| GET `/api/status` | `{broker: orion-ld or fallback, whatsapp_configured, yext_entity: SinceAI07, today, public_url, voice}` |
| POST `/api/reset` | demo reset: `YextSandbox.reset_demo` (zero holiday rows), all suggestions and events cleared, broker entity re-created with status missing (no proposed instance), clock set to 2026-12-17; `?learn=1` also clears learned prefs. Returns status plus `reset` details |
| POST `/api/stub/decide/{id}?action=approve` | releases the stub decide step when `KAIKU_STUB_DECIDE=wait` |

## Event schema
`{id, ts (ISO UTC), step: detect|suggest|contact|decide|apply|learn|broker, business_id, suggestion_id, title_fi, title_en, detail: {}}`.
`kaiku.events.emit(Event)` is safe from sync code, threads and the loop. UI convention: `detail.phase = "waiting"` on a decide event means the owner has not answered yet; `detail.error` marks a failure (row turns red).

## Registry contract (other modules)
Import `kaiku.chain` and call `chain.register(name, fn)` at import time of your module (sync or async functions both work):
```
detect(business: Business, holiday_date: str, now: datetime) -> Detection
suggest(business: Business, detection: Detection) -> Suggestion
contact(suggestion: Suggestion) -> None            # emits its own events, sends, appends suggestion.channel_log, saves via store.save_suggestion
decide(suggestion: Suggestion) -> Decision         # awaits the owner (async); you emit your own decide events if you want more than core's two
apply(suggestion: Suggestion, decision: Decision) -> ApplyResult
learn(suggestion: Suggestion, decision: Decision) -> None
```
`holiday_date` is "YYYY-MM-DD". Core emits: detect, suggest, decide (waiting, then decided), apply and learn events after each real call returns, so implementations of those four need not emit. `contact` must emit its own (core emits nothing for it). Decline skips apply. Stubs sleep `KAIKU_STEP_GAP` (1 s) before each step only while the stub is in place. Stub decide auto-approves after 3 s unless `KAIKU_STUB_DECIDE=wait`. Stub apply writes nothing and says so. Decision made outside the chain (web page, WhatsApp webhook) must resolve the awaiting `decide` future you own.
Routers: expose `router = APIRouter()` in `kaiku/<module>/router.py`; app.py includes broker, contact, decide, voice, map, learn, mcp_bridge, aura if importable.

## Store
SQLite (WAL) at `data/kaiku.sqlite`: tables businesses, suggestions, decisions, events, prefs (JSON columns). `store.seed()` loads `data/furry_paw.json`; owner_whatsapp is injected from env, never stored in the file. The seed is labelled sample history: last-year hours are fictional, written by the team.

## Home time travel (6 Nov)
Run button: if the picked holiday is before the fake today (or >21 days ahead) the page first calls `/api/timetravel?date=<holiday-6d>` (24.12. far-off: -7d = 17.12.), refreshes the Today label, shows a 2 s note, then POSTs /api/run. A date input under the picker (`#tt-date`) sets today directly; reset reloads with the picker on 24.12. (`autocomplete=off`).

## What did not work / notes
Body background hid the fixed gradient stage (negative z-index); fixed by making body transparent. Cloudflare cached css for 4 h; fixed as above.

## Wiring (integration, 6 Nov)
`chain.py` installs the real steps at import, each guarded (a missing module keeps its stub):
- detect and suggest: `kaiku.detect.engine.detect` and `kaiku.suggest.engine.suggest` through adapters (pydantic Business to their dataclasses and back), run in a thread. `now` is `learn.timetravel.now()`. Core keeps its own suggestion id. Then `learn.prefs.apply_prefs`, then `decide_url` from `kaiku.decide.tokens.link_for` (placeholder `PUBLIC_URL/d/<id>` if decide is absent).
- contact: `chain.contact_step` is re-registered by app.py after `kaiku.contact.ladder` import, because the ladder registers a dict-taking function against the Suggestion contract. With WhatsApp configured it calls the ladder in a thread. Degraded rule: without WA_TOKEN no message leaves; the event says "WhatsApp ei ole vielä käytössä, päätöslinkki valmis" with `detail {decide_url, message_fi, degraded}`, the channel_log records BLOCKED and "call lane not configured", and the chain continues. For `no_change` no decision is asked: decide, apply and learn emit "skipped" events.
- decide: the real step from `kaiku.decide` (waits up to 600 s for the link; the stub auto-approve only remains if that module is missing). `chain.on_decision(decision)` resolves `decide.resolve`, else the stub future. Decline skips apply; action `timeout` stops the chain without writing.
- apply: `kaiku.apply.apply_suggestion("SinceAI07", date, hours)` (real sandbox write, read-back `verified`), event carries `where_it_shows`. Receipt via `contact.router.send_receipt` only if WhatsApp is configured.
- learn: `learn.prefs.record_decision`, learn event says what was learned.
- broker: before detect status `missing`; after suggest the `proposed` datasetId instance; after apply the default instance and status `applied` (broker docs enum). Failures emit "Broker ei vastaa" and never stop the chain. Lifespan seeds the entity and calls `ensure_subscriptions()`.
Tests: `python3 -m pytest -q` (offline; `live`/`network` markers skipped unless KAIKU_LIVE=1; conftest points sqlite and data dir at temp).
