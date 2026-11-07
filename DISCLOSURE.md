# DISCLOSURE: brought versus built (kept true at all times)

## The three hard questions
1. Who is it for? The owner of a small business whose hours Fonecta Connect publishes. The demo business is the fictional Furry Paw Vet Clinic (Fonecta's sandbox entity SinceAI07).
2. Built versus pre-existing: see below. Brought: vendored MIT voice-pilot, `/root/hack/bin` process scripts, public APIs and data, the Yext sandbox, our VPS and Cloudflare tunnel. Everything else was written during the event, after bell commit e2f7382.
3. What breaks first at scale: the suggestions engine's per-business web fetches (website and Google signals, per holiday, cached 30 s; 6 HTTP calls and 1.6 s warm for the demo clinic on 7 Nov 2026). See ARCHITECTURE.md.

## Built
First commit: e2f7382, the bell commit, Fri 6 Nov 2026 18:49:59Z, a fresh repo with conventions only and no code. All application code in this repository was written during the event after it,
with AI coding tools (Claude Code: Fable orchestrating, Sonnet builders and verifiers). Everything not listed under "Brought" is
written after that commit.

## Brought (declared)
- voice-pilot, github.com/oroomi/voice-pilot (our own, MIT, published 18 Oct 2026), vendored under vendor/voice-pilot with its
  licence. The design is reused; the server code was rewritten during the event.
- maplibre-gl 4.7.1, vendored (BSD-3-Clause).
- Map tiles: OpenFreeMap. Map data: OpenStreetMap via Overpass (ODbL).
- Live feeds: Föli SIRI VM, Fintraffic Digitraffic AIS, Open-Meteo (all CC BY 4.0).
- Nager.Date public holidays API; Smart Data Models contexts.
- Services run unmodified: Orion-LD (FIWARE NGSI-LD context broker, AGPL-3.0) and MongoDB, as Docker images.
- ngsi-ld-mcp (`ngsi-ld-mcp/`, MIT, The Mishakin Group) is our own, written during the event.
- Email: SMTP through Zoho (our account); the owner address is a team member's own. Proof: `data/email_log.jsonl`, sent 2026-11-06T23:48:04Z.
- Services: ElevenLabs Agents (outbound call via SIP trunk) and Zadarma (SIP trunk provider; the caller ID is the team member's own number).
- Libraries and APIs: mcp Python SDK, Anthropic SDK (model claude-sonnet-5-5), ElevenLabs API (TTS and STT), Yext sandbox API
  (entity provided by Fonecta), Serper (Google places lookup), Meta WhatsApp Cloud API (test number).
- Infrastructure: our VPS, domain, and a Cloudflare tunnel.
- /root/hack/bin scripts (pre-existing process tooling, not product code): deploy, shot, smoke, expose.

## Mocked or not live
- Contact ladder: email, then one WhatsApp text after `EMAIL_ESCALATE_AFTER_S` (60 s live config), then a call after `WA_ESCALATE_AFTER_S` (36000 s live config, so the phone does not ring unprompted). WhatsApp buttons are off unless `WA_BUTTONS=1`.
- Demo language: the whole demo is English (web copy, WhatsApp opener with two buttons Accept / Discard, the decision page, the phone call). Finnish stays available per owner (`owner_language`). The English WhatsApp template `kaiku_hours_en` (quick replies Approve / Edit / No thanks, the template wording; the live interactive opener uses Accept / Discard) was submitted to Meta on 6 Nov 21:49Z and is pending, like `kaiku_hours_fi`.
- WhatsApp: the Meta Cloud API token (test number +1 555 188 5173, Meta test WABA) was configured on 6 Nov 2026 at 20:19Z. Test messages were sent only to the team's own phone (the owner number in demos is a team member's own, with consent); Meta delivery callbacks are stored in `data/wa_status.jsonl`. Free-form and button messages only deliver inside Meta's 24 hour customer-service window (the owner's phone must message the test number first); templates deliver at any time. The Finnish utility template `kaiku_hours_fi` (three quick-reply buttons) was submitted on 6 Nov 20:28Z and is pending Meta approval; The English WhatsApp template `kaiku_hours_en` (quick replies Approve / Edit / No thanks) was submitted to Meta on 6 Nov 21:49Z and is pending, like `kaiku_hours_fi`. The code path is behind `WA_TEMPLATE_NAME` / `WA_TEMPLATE_NAME_EN` and off until approval (`docs/whatsapp.md`). Without a working WhatsApp send the contact step produces the decision link instead. Client unit tests use a fake transport; live-sending tests run only with `KAIKU_LIVE=1`.
- Call lane (ElevenLabs outbound call, English; Finnish per owner): on main (`kaiku/contact/call.py`): ElevenLabs Agents creates the agent (gemini-2.0-flash with an English system prompt (Finnish kept per owner) and a `data_collection` field `action` with approve, edit or decline), the number is a SIP trunk (provider `sip_trunk`, `ELEVENLABS_PHONE_PROVIDER=sip_trunk`, no Twilio), decision webhook `/webhooks/call`. The outbound call works: on 6 Nov 2026 at 21:24Z (`data/call_log.jsonl`) a call was answered by the team's own phone, the Kaiku agent (then still Finnish) spoke its opening line ("Hei, täällä Kaiku, Fonecta Connectin avustaja..."), the call lasted 37 s, and the ElevenLabs post-call webhook reached `POST /webhooks/call` (HTTP 200). The earlier SIP 488 (20:12Z and 20:23Z) was caused by the Zadarma SIP trunk rejecting offers with media encryption; the ElevenLabs trunk setting for media encryption was changed from "allowed" to "disabled" on 6 Nov 2026 at about 21:21Z (a dashboard edit, no code change for that part). Later dials at 21:27Z (SIP 408 Ringing Timeout) and 21:31Z (SIP 480 Temporarily Unavailable) were simply not answered. The agent was then switched to English (language en, `eleven_flash_v2`: "Hi, this is Kaiku, the Fonecta Connect assistant..."). Proven end to end on 6 Nov 2026: at 21:46:53Z (`data/call_log.jsonl`, suggestion `6f1bd3dfdf`, business furry-paw, conversation `conv_8001m6sd85c3eqya7a17c1wkgmwk`) Kaiku phoned the team's own phone in English, the owner approved on the call, the post-call webhook created the Decision (via "call"), and Yext received 24.12. 9-13, read back and verified. The WhatsApp path has been proven end to end with a real Yext write at 20:42Z. Calls were made only to the team's own phone. The WhatsApp step escalates to the call after `WA_ESCALATE_AFTER_S` seconds (default 120; the live config sets 36000).
- Google signal (Serper): `SERPER_API_KEY` is set and `google_now` (`kaiku/detect/signals.py`) calls Serper places, but the demo business is fictional, so it returns no hours and the status is unknown.
- Security: the public events feed and suggestion endpoints do not carry the owner's decision link unless the viewer holds the demo key (cookie set by `?key=`, or `X-Kaiku-Key` header). httpx request logging is off so API keys never reach the journal. The demo reset also clears pending MCP proposals. Delivery statuses are logged.
- Peer priors (`data/peer_priors.json`) are hand-made; website parsing is tested on a mocked page.
- The Yext Suggestions API returns 403 for the sandbox key; Apply writes the entity through the Management API instead (docs/apply.md).
- The sandbox entity had no description and no reviews, so the team wrote a sample description (it says so in its last sentence) and two sample reviews labelled "Sample reviewer (fictional)" (`data/furry_paw_description_sample.txt`, `data/furry_paw_reviews_sample.json`, `tools/seed_sandbox.py`). The description and review cards on the live page work on that sample text; the sandbox key cannot post review replies, so an approved reply is stored, not posted.
- Yext sandbox has no publisher listings: the write is real, the syndication to Google and others is not.
- Room answers on `/map` are demo data and are not written to Yext.

## Fictional data
"Furry Paw Vet Clinic" is Fonecta's sandbox business; its history is a labelled sample we wrote.

## GenAI in the product
Claude claude-sonnet-5-5: the chat brain (three tools: decide, standing permission, ask; 40-word cap; keyword parser fallback), the voice tool loop and the Aura subscription proposals. ElevenLabs: speech to text (scribe_v1), text to speech and the call agent. The suggestion engine and its messages are rules and templates, not a model. The coding was done with Claude Code.

## Data sources and licences
See docs/DATA_SOURCES.md.

## Sample description and sample reviews (declared)
The Yext sandbox entity SinceAI07 has no description and no reviews. We wrote one sample description (with a deliberate typo,
"vacination") and two sample reviews ("Sample reviewer (fictional)") ourselves and put them in the sandbox through the Management and
Reviews APIs (`tools/seed_sandbox.py`; fallback file `data/furry_paw_reviews_sample.json`). They are fictional, labelled as such in the text
and in every card's reason row. Typo corrections and review replies are drafted by Anthropic claude-sonnet-5-5 (GenAI) and only applied after the owner approves.
