# DISCLOSURE: brought versus built, and what is sample data (kept true at all times)

Last checked against the live product on 7 Nov 2026, about 11:30Z (https://kaiku.hankintaviikko.fi).

## The three hard questions
1. Who is it for? The owner of a small business whose hours Fonecta Connect publishes. The demo business is the fictional Furry Paw Vet Clinic (Fonecta's sandbox entity SinceAI07).
2. Built versus pre-existing: see below. Brought: vendored MIT voice-pilot, `/root/hack/bin` process scripts, public APIs and data, the Yext sandbox, our VPS and Cloudflare tunnel. Everything else was written during the event, after bell commit e2f7382.
3. What breaks first at scale: the suggestions engine's per-business web fetches (website and Google signals, per holiday, cached 30 s; 6 HTTP calls and 1.6 s warm for the demo clinic on 7 Nov 2026). See ARCHITECTURE.md.

## Built
First commit: e2f7382, the bell commit, Fri 6 Nov 2026 18:49:59Z, a fresh repo with conventions only and no code. All application code in this repository was written during the event after it, with AI coding tools (Claude Code: Fable orchestrating, Sonnet builders and verifiers; the team is one person on site, Dayo, who decided the product and runs the demo). Everything not listed under "Brought" is written after that commit. This includes the owner page, the contact ladder, the console, the /eval page, the FIWARE spine, the `ngsi-ld-mcp` server and Aura (the FIWARE entry).

## Brought (declared)
- voice-pilot, github.com/oroomi/voice-pilot (our own, MIT, published 18 Oct 2026), vendored under `vendor/voice-pilot` with its licence. The design is reused; the server code was rewritten during the event.
- maplibre-gl 4.7.1, vendored (BSD-3-Clause). Fonts Inter, Newsreader, IBM Plex Mono (SIL OFL), vendored.
- Map tiles: OpenFreeMap. Map data: OpenStreetMap via Overpass (ODbL).
- Live feeds: Föli SIRI VM, Fintraffic Digitraffic AIS, Open-Meteo (all CC BY 4.0).
- Nager.Date public holidays API; Smart Data Models contexts.
- Services run unmodified: Orion-LD (FIWARE NGSI-LD context broker, AGPL-3.0) and MongoDB, as Docker images.
- `ngsi-ld-mcp/` (MIT, The Mishakin Group) is our own, written during the event.
- Email: SMTP through Zoho (our account); the owner address is a team member's own. Proof on the demo host: `data/email_log.jsonl` (not committed), first send 2026-11-06T23:48:04Z.
- Phone: ElevenLabs Agents (the call agent, voice Aurora, speech model eleven_v4, speech to text scribe_v1) and Zadarma (SIP trunk provider; the caller ID is the team member's own number).
- Libraries and APIs: mcp Python SDK, Anthropic SDK (model claude-sonnet-5-5), Yext sandbox API (entity provided by Fonecta), Serper (Google places lookup), Meta WhatsApp Cloud API (test number).
- Infrastructure: our VPS, domain, and a Cloudflare tunnel.
- `/root/hack/bin` scripts (pre-existing process tooling, not product code): deploy, shot, smoke, expose.
- Film (Kaiku and Aura videos): made with Remotion, our own capture scripts and our own trailer motion template (team tooling from before the event, not product code). Music: the licensed cut uses "Hype Beat" (Pixabay licence); the alternative cut uses "Victory Lap" by Fred again.. and Skepta, for which we hold no licence (YouTube Content ID may claim or mute it). The `video/` folder is not in the public repo.

## What is sample data and what is real
| Item | Real or sample | Where to see it |
|---|---|---|
| Furry Paw Vet Clinic | Fictional business. The Yext entity SinceAI07 was provisioned by Fonecta; name, address (Tikkurilantie 9, Vantaa) and category come from it | `GET /api/listing/furry-paw` |
| Regular opening hours | Set by us on the sandbox entity on 6 Nov | same |
| Last year's exception hours (24.12. 9-13) | Sample history written by us, because the sandbox holds none | `data/furry_paw.json` |
| Description, with the deliberate typo "vacination" | Sample text written by us, says so in its last sentence | `data/furry_paw_description_sample.txt` |
| The two reviews | Sample reviews, "Sample reviewer (fictional)", put into the sandbox by us | `data/furry_paw_reviews_sample.json`, `tools/seed_sandbox.py` |
| Website of the clinic | Does not exist; the website signal returns nothing | `docs/DATA_SOURCES.md` source 3 |
| Peer priors (what similar businesses do) | Hand-made by us, labelled | `data/peer_priors.json` |
| Google signal | Real call to Serper; for a fictional clinic it returns "unknown" | `kaiku/detect/signals.py` |
| Today's date in the demo (17.12.2026) | Fake, set with time travel so Christmas can be shown in November | `/api/status` field `today` |
| Public holidays | Real, Nager.Date | `data/holidays_fi_2026.json` |
| Yext write and read-back | Real writes to Fonecta's sandbox entity. The sandbox has no publisher listings, so nothing is syndicated to Google or anywhere else | `GET /api/listing/furry-paw` |
| Email, WhatsApp message, phone call | Real messages and calls, sent only to the team's own email and phone (and to a visitor's own, with consent, through the console) | `docs/call.md`, `docs/whatsapp.md` |
| Listing score | Computed live from what the sandbox holds | `GET /api/score/furry-paw` |
| Evaluation cases | 10 cases written by us; self-consistency only, not accuracy | `data/sample_cases.json`, EVAL.md |
| /eval results | Computed in the request from the file you drop (or our 10 cases) | `/eval` |
| Turku map businesses | Real, 813 OpenStreetMap businesses; the answers visitors give on `/map` are demo data and are never written to Yext | `data/turku_businesses.json` |
| Aura buses, ships, weather | Real live feeds | `GET /api/aura/status` |

## Mocked or not live
- Fonecta gave no dataset format and no sample data during the event. Nothing in this repo was tested on Fonecta data. See EVAL.md.
- Contact ladder, live configuration: an email with the decision link at once, a WhatsApp message with two buttons (Accept, Discard) after `EMAIL_ESCALATE_AFTER_S` = 60 s, a phone call after `WA_ESCALATE_AFTER_S` = 600 s. A decision on any channel cancels the next step. The order changes after the owner answers the closing question ("how would you like to be reached next time"): the stored preference puts WhatsApp or the call first (`docs/learn.md`).
- Demo language: the demo is English (web copy, WhatsApp, decision page, phone call). Finnish stays available per owner (`owner_language`).
- WhatsApp: Meta Cloud API test number (+1 555 188 5173, Meta test WABA). Messages go only to numbers registered in the Meta test app (the team's own, or a visitor who registered theirs). Free-form and button messages only deliver inside Meta's 24 hour customer-service window (the owner's phone must message the test number first); templates deliver at any time. The utility templates `kaiku_hours_fi` and `kaiku_hours_en` were submitted on 6 Nov and were pending Meta approval at last check, so outside the window the test number's `hello_world` template goes first. Client unit tests use a fake transport; live-sending tests run only with `KAIKU_LIVE=1`.
- Call lane (`kaiku/contact/call.py`, `docs/call.md`): an ElevenLabs Agents agent whose language model is gemini-2.0-flash (Google, run by ElevenLabs), speaking English with the voice Aurora on the eleven_v4 speech model, dialled out through a SIP trunk (provider `sip_trunk`, Zadarma, no Twilio). When the call ends ElevenLabs posts the transcript to `POST /webhooks/call`, which turns the owner's words into a decision (or an edit, or a stored channel preference). Truthful history: the first answered call was 6 Nov 21:24Z; the English call that the owner approved on the phone, which wrote 24.12. 9-13 to Yext and was read back, was 6 Nov 21:46:53Z; the voice and script were then re-done on 7 Nov, and the latest calls were placed on 7 Nov at 10:18:34Z and 10:23:22Z (`data/call_log.jsonl` on the demo host, not committed). Calls were made only to the team's own phone.
- Standing permission: stored per holiday or for all. On the next run for that holiday the chain applies without asking and tells the owner afterwards in one line (`kaiku/chain.py`, `tests/test_core.py::test_standing_permission_applies_without_asking`). Not shown live end to end on a second year, because the demo clock only covers one Christmas.
- Promise wording: every message says "We'll update your information everywhere" and does not list publishers. This is a statement of what Connect does in production. In the sandbox the write is real but nothing is syndicated (no publisher listings), and the receipts say "saved" because the Yext read-back matched.
- The Yext Suggestions API returns 403 for the sandbox key; Apply writes the entity through the Management API instead (`docs/apply.md`). The sandbox key cannot post review replies, so an approved reply is stored, not posted.
- Security: the public events feed and suggestion endpoints do not carry the owner's decision link unless the viewer holds the demo key. `/judge` and `/console` need the demo key. httpx request logging is off so API keys never reach the journal. Test servers and the test suite are silent by design (no email, WhatsApp or call leaves except from the production URL).

## GenAI in the product
- Anthropic claude-sonnet-5-5: the chat brain (three tools: decide, standing permission, ask; 40-word cap; keyword parser fallback), the voice tool loop on the website, the drafted review replies and description corrections (applied only after the owner approves), and the Aura subscription proposals.
- ElevenLabs: speech to text (scribe_v1), text to speech (eleven_v4, voice Aurora) and the phone agent, whose language model is Google gemini-2.0-flash.
- The suggestion engine and its messages are rules and templates, not a model. The coding was done with Claude Code.

## Data sources and licences
See docs/DATA_SOURCES.md.

## Open items to settle before submission
- The film: the music bed and the trailer template are declared above under "Brought"; the `video/` folder is removed from the public repo (see docs/SUBMISSION.md, "At submission time").
- A team member's personal phone number appears in the git history (and in a test file and one doc line until the removal list is run). Decision recorded in docs/SUBMISSION.md.
