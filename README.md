# Kaiku: Connect suggests, the customer approves

**What and for whom.** Kaiku is the whole chain for holiday hours (Detect, Suggest, Contact, Decide, Apply) for the owner of a small business whose opening hours Fonecta Connect publishes. The owner gets a message instead of a login, answers in plain words ("yes", "make it 10-14", "no thanks"), and the approved hours are written to Fonecta's Yext sandbox. The demo business is the **fictional** Furry Paw Vet Clinic, Fonecta's sandbox entity SinceAI07 in Vantaa.

**Live:** <https://kaiku.hankintaviikko.fi> (phone and laptop) | **Demo video:** approval cut rendering on 7 Nov (sample pages); the final cut on the live page follows, YouTube link at submission | **Repo:** github.com/oroomi/kaiku
**Challenge:** Fonecta, "Connect suggests, customer approves" | **Partner technology:** FIWARE (Orion-LD NGSI-LD broker) | **Team:** VY7, solo (Dayo) with Claude coding tools

![Kaiku home: Furry Paw Vet Clinic, Christmas Eve, Connect 9-17 versus Kaiku 9-13](docs/img/hero.jpg)
(Screenshot of an earlier home; the owner page changed on 7 Nov, see [docs/owner.md](docs/owner.md).)

## Run it in 3 commands
```bash
git clone https://github.com/oroomi/kaiku && cd kaiku
python3 -m venv .venv && .venv/bin/pip install -r requirements.txt
.venv/bin/uvicorn kaiku.app:app --host 127.0.0.1 --port 8210   # http://127.0.0.1:8210
```
Without keys the chain still runs and each lane says what is missing. Tests: `.venv/bin/python -m pytest -q` gives 415 passed, 6 skipped on main with the box's `.env` (run 7 Nov 2026; the skipped ones send or fetch live and need `KAIKU_LIVE=1`). In a fresh checkout without SMTP settings `tests/test_email.py::test_real_smtp_path` also fails (414 passed, 1 failed (test_real_smtp_path, needs the box .env)). The suite sets `KAIKU_NO_SMTP=1`, `KAIKU_FEED_NETWORK=0` and an empty `WA_TOKEN`, so it never sends or fetches.

## How this meets the brief
Fonecta's slide 8 and slide 7, answered item by item (all numbers re-checked on the live product, 7 Nov 2026, main 96d279d):
- **What to submit** (working demo, video, repo, data sources, final messages, cold start, deck, bonus): [docs/SUBMISSION.md](docs/SUBMISSION.md), one row per item with its link.
- **Data sources, production source, what did not work:** [docs/DATA_SOURCES.md](docs/DATA_SOURCES.md). **Final customer messages as text:** [docs/final_messages.md](docs/final_messages.md). **No history:** [docs/COLD_START.md](docs/COLD_START.md). **Pitch deck:** [docs/DECK.md](docs/DECK.md).
- **Evaluation criteria** (suggestion quality, customer experience, reliability, extensibility, learning, all five steps): each answered in one paragraph with evidence at the end of [EVAL.md](EVAL.md). Honest status: Fonecta's hidden dataset is unknown to us, so suggestion quality is a self-consistency check on 10 cases we wrote, with a loader (`kaiku.suggest.backtest.load_cases`) that accepts CSV or JSON.
- **Bonus** (a live source replacing a dataset file): [docs/DATA_SOURCES.md](docs/DATA_SOURCES.md) "Bonus".
- **One deliberate difference from Fonecta's example:** the WhatsApp opener has two buttons, Accept and Discard, and an edit is typed ("To change the hours, just reply with them"), instead of Approve / Edit / No thanks. One tap for the two common answers; a typed edit carries the actual hours.

## The three hard questions
1. **Who is it for?** The owner of a small business whose hours Fonecta Connect publishes and who forgets one-off changes such as holiday hours (a vet, a cafe, a salon). Not chains with a marketing team. The demo owner is fictional.
2. **What was built this weekend?** Everything in this repo from the bell commit `e2f7382` (6 Nov 2026 18:49:59Z) on, except what [DISCLOSURE.md](DISCLOSURE.md) lists as brought: our MIT voice-pilot (vendored), `/root/hack/bin` process scripts, public APIs and data, the Yext sandbox, our VPS and Cloudflare tunnel.
3. **What breaks first at scale?** The suggestions engine fetches signals per business on every build (the business website and Google via Serper, per holiday). On 7 Nov 2026 one build for the demo clinic made 6 HTTP calls and took 1.6 s warm; with more holidays in view and a real website the number and the cold time grow per business, and the result is cached only 30 s. That is the first wall; the chat paints its first screen on the quick path without network signals for this reason. Second: our Orion-LD build cannot update a datasetId instance in place (see [ARCHITECTURE.md](ARCHITECTURE.md)).

## What the owner sees (`/`)
The hero is the **listing score** (0-100 and "3 of 7 checks" on 7 Nov: regular hours, holiday hours, sources agree, description, reviews answered, address and category, website or phone), computed from what Yext holds ([docs/score.md](docs/score.md)). Below it, one **card** per suggestion (holiday hours, a holiday period, a description correction, a review reply, conflicting sources, "no change" notes), each with **Accept**, **Suggest a change** and a faint **Discard**; every card carries its reason. **Accept applies at once**: the hours are written to Yext and read back. The **chat with Kaiku** opens empty; after an action Kaiku confirms with a receipt, asks "Do you want to make it recurring, this time of the year?" only when last year's data exists, then moves on to the next item. "Suggest a change" starts a typed edit ("make it 10-14" gives "10-14 on 24.12., shall I save it?"). The voice orb feeds the same chat. **On Fonecta now** shows what Yext holds, with missing values as "no data". The sandbox description and the two reviews are sample text written by team VY7 and labelled so. Demo controls (time travel, holiday picker, Run the chain, Reset) are in the keyed drawer `/?key=...#drawer`; `/judge` (keyed) shows live events, broker, WhatsApp and Yext chips and the Yext read-back. Details: [docs/owner.md](docs/owner.md), [docs/chat.md](docs/chat.md).

## Contact ladder
1. **Email** with the decision link (SMTP via Zoho, address from `OWNER_EMAIL`). Live proof: sent 2026-11-06T23:48:04Z, suggestion `1e5f6eff7a` (`data/email_log.jsonl`).
2. After `EMAIL_ESCALATE_AFTER_S` (60 s in the live config, code default 120) with no decision: **a WhatsApp opener**: a warm text in Kaiku's voice about one item, with two buttons, **Accept** and **Discard**, under it and the line "To change the hours, just reply with them." It is the same conversation as the website chat: replies go to the same brain and the same decision path (`WA_BUTTONS=0` sends the plain-text variant). Live proof: first WhatsApp text sent 2026-11-06T23:49:08Z (`data/wa_sends.jsonl`; the Accept / Discard layout shipped on 7 Nov); earlier a WhatsApp tap wrote to Yext at 20:42Z ([docs/whatsapp.md](docs/whatsapp.md)).
3. After `WA_ESCALATE_AFTER_S` (code default 120; the live config sets 36000 so the phone does not ring unprompted): **a phone call by Kaiku** (ElevenLabs agent over a Zadarma SIP trunk, English). Live proof: call answered, owner approved, Yext write at 21:46:53Z, `data/call_log.jsonl` ([docs/call.md](docs/call.md)).
A decision on any channel cancels the next step.

## The brain
Anthropic claude-sonnet-5-5 with three tools (decide, set_standing_permission, get_feed), a 40-word reply cap, and a deterministic keyword parser that answers when the model is unavailable. A plain yes, a tap, an hours value and the receipt are handled without the model (`kaiku/chat/flow.py`), so they are fast and cannot overclaim. After an approval Kaiku asks once, only when last year's data exists: "Do you want to make it recurring, this time of the year?" ([docs/whatsapp.md](docs/whatsapp.md), `kaiku/chat/brain.py`).

## Demo path
Set the clock to 17.12.2026 (the live default). Open `/`: the cards show Christmas Eve 24.12. 9-13 against Connect's 9-17 and the Christmas period of 6 dates, 24.12. to 6.1. Press **Accept** (or tap Accept in the WhatsApp message, or use the email link): the hours are written to Yext and read back, Kaiku confirms, then asks about making it recurring. With the clock at 7.11. the cards show Father's Day 8.11. as "no change needed" (a flag day, the clinic is closed on Sundays). Details: [DEMO_SCRIPT.md](DEMO_SCRIPT.md).

## Architecture
```mermaid
flowchart LR
  subgraph Sources
    S1[Holidays: Nager.Date]:::s
    S2[Own hours + last year: Connect/Yext]:::s
    S3[Website, Google via Serper, peer priors]:::s
  end
  S1 & S2 & S3 --> ORION[(Orion-LD broker\none datasetId per source)]
  ORION -- subscription fires --> DET[Detect]
  DET --> SUG[Suggest + confidence gate]
  SUG -- proposed instance --> ORION
  SUG --> CON[Contact ladder:\nemail, WhatsApp text, call]
  CON --> DEC[Decide: chat in words\nor /d/token link]
  DEC -- default instance --> ORION
  DEC --> APP[Apply: Yext Management API\nholidayHours write + read-back]
  DEC --> LRN[Learn: prefs, standing permission]
  classDef s fill:#163746,color:#fff
```
The broker is the spine: each source writes its own instance of `holidayHours` (a `datasetId` per source); a subscription fires Detect, the engine adds a `proposed` instance, the owner's answer writes the default instance, and Apply writes Yext. The Yext write never depends on the broker (`broker/fallback.py`). Apply uses the Yext Management API directly; the Yext Suggestions API returns 403 for the sandbox key ([docs/apply.md](docs/apply.md)). Details: [ARCHITECTURE.md](ARCHITECTURE.md).

## FIWARE
Orion-LD is the spine of the chain: one business, five datasetIds, one truth (`holidayHours` has one instance per source, the default instance is the owner-approved truth), subscriptions that fire the chain, and an MCP agent (`ngsi-ld-mcp/`) that can propose but never decide. Open **[/fiware](https://kaiku.hankintaviikko.fi/fiware)** (read-only, every figure read live) and read the narrative in **[docs/fiware.md](docs/fiware.md)**; the broker details are in [docs/broker.md](docs/broker.md).

## Evaluation
Honest answer: on 10 cases we wrote ourselves, wrong-suggestion rate 0.0 and abstain rate 0.2. That is a self-consistency check, not accuracy; we have no Fonecta dataset or scoring script yet. Reliability in the product: a confidence gate (below 0.6 Kaiku asks and proposes nothing), "no change" shown as a note, and a question instead of a guess when sources conflict. See [EVAL.md](EVAL.md).

## Disclosure
All application code was written after the bell commit e2f7382. Brought: our MIT voice-pilot (vendored), `/root/hack/bin` scripts, public data and services, the Yext sandbox, our VPS. See [DISCLOSURE.md](DISCLOSURE.md).

## Configuration and services
Optional, in `.env` (never committed): `YEXT_API_KEY`, `ANTHROPIC_API_KEY`, `ELEVENLABS_API_KEY`, `SERPER_API_KEY`, `SMTP_HOST`/`SMTP_USER`/`SMTP_PASS`/`SMTP_FROM`, `OWNER_EMAIL`, `OWNER_WHATSAPP`, `WA_TOKEN`, `WA_PHONE_ID`, `EMAIL_ESCALATE_AFTER_S`, `WA_ESCALATE_AFTER_S`. FIWARE spine: `docker-compose -f kaiku/broker/docker-compose.yml up -d` starts Orion-LD on 127.0.0.1:1026; without it an in-memory fallback runs and events say "broker offline" ([docs/broker.md](docs/broker.md)).
WhatsApp: Meta Cloud API test number, messages only to the team's own phone; free-form messages deliver only inside Meta's 24 hour window; the templates `kaiku_hours_fi` and `kaiku_hours_en` were submitted on 6 Nov and were pending at last check. Security: the public events feed and suggestion endpoints omit the decision link unless the viewer holds the demo key; httpx request logging is off.

## What runs
| Part | Where | Doc |
|---|---|---|
| Chain, SSE events, SQLite | `kaiku/` | [docs/core.md](docs/core.md) |
| Owner page: chat, thread, suggestion cards | `kaiku/chat`, `kaiku/web` | [docs/owner.md](docs/owner.md) |
| Detect and Suggest, confidence gate, cold start | `kaiku/detect`, `kaiku/suggest` | [docs/suggest.md](docs/suggest.md) |
| Orion-LD spine | `kaiku/broker` | [docs/broker.md](docs/broker.md) |
| Contact ladder: email, WhatsApp, call | `kaiku/contact` | [docs/contact.md](docs/contact.md), [docs/whatsapp.md](docs/whatsapp.md), [docs/call.md](docs/call.md) |
| Decide: chat or `/d/<token>` | `kaiku/decide`, `kaiku/chat` | [docs/decide.md](docs/decide.md) |
| Apply: Yext write, read-back, snapshot, revert | `kaiku/apply` | [docs/apply.md](docs/apply.md) |
| Learn: preferences, standing permission, clock | `kaiku/learn` | [docs/learn.md](docs/learn.md) |
| Voice | `kaiku/voice` | [docs/voice.md](docs/voice.md) |
| Map and room (813 real OSM Turku businesses) | `kaiku/map` | [docs/map.md](docs/map.md) |
| Aura (FIWARE entry) and ngsi-ld-mcp | `kaiku/aura`, `ngsi-ld-mcp/` | [docs/aura.md](docs/aura.md), [docs/mcp.md](docs/mcp.md) |

Submission texts: [docs/SUBMISSION.md](docs/SUBMISSION.md). Data sources: [docs/DATA_SOURCES.md](docs/DATA_SOURCES.md). Cold start: [docs/COLD_START.md](docs/COLD_START.md). Final messages: [docs/final_messages.md](docs/final_messages.md). Deck: [docs/DECK.md](docs/DECK.md).

## Libraries and licences
Every entry of `requirements.txt`, with the licence its installed package declares (checked 7 Nov 2026 with `importlib.metadata`):
| Package | Licence | Package | Licence |
|---|---|---|---|
| fastapi 0.162.0 | MIT | pydantic 2.14.3 | MIT |
| starlette 1.10.0 | BSD-3-Clause | httpx 0.28.1 | BSD-3-Clause |
| uvicorn 0.54.0 | BSD-3-Clause | h11 0.16.0 | MIT |
| httptools 0.9.0 | MIT | uvloop 0.23.0 | MIT / Apache-2.0 |
| websockets 17.4 | BSD-3-Clause | watchfiles 1.3.0 | MIT |
| anyio 4.16.0 | MIT | click 8.5.1 | BSD-3-Clause |
| Jinja2 3.1.6 | BSD-3-Clause | python-dotenv 1.2.4 | BSD-3-Clause |
| PyYAML 6.0.3 | MIT | qrcode 8.2 | BSD |
| anthropic (SDK) 2.6.0 | Apache-2.0 | mcp (Python SDK) | MIT |
| playwright 1.64.1 (screenshots) | Apache-2.0 | pytest 9.2.0 | MIT |
| pytest-asyncio 1.4.1.post1 | Apache-2.0 | ngsi-ld-mcp (ours, `ngsi-ld-mcp/`) | MIT |

Also: MapLibre GL JS 4.7.1 (BSD-3-Clause, vendored); voice-pilot (ours, MIT, vendored under `vendor/voice-pilot`); fonts Inter, Newsreader, IBM Plex Mono (SIL OFL, vendored); Orion-LD (AGPL-3.0, run unmodified as a Docker image, not linked); MongoDB (run as a container image). Data licences are in [docs/DATA_SOURCES.md](docs/DATA_SOURCES.md).

## Pilot
Eight weeks with Fonecta Connect on real exception-hours data: [PILOT.md](PILOT.md).

## Team
VY7, solo: Dayo (product, pitch, phone). Code written with Claude Code (Fable orchestrating, Sonnet builders and verifiers).
