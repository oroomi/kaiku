# DISCLOSURE: brought versus built (kept true at all times)

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
- Libraries and APIs: mcp Python SDK, Anthropic SDK (model claude-sonnet-5-5), ElevenLabs API (TTS and STT), Yext sandbox API
  (entity provided by Fonecta), Serper (Google places lookup), Meta WhatsApp Cloud API (test number).
- Infrastructure: our VPS, domain, and a Cloudflare tunnel.
- /root/hack/bin scripts (pre-existing process tooling, not product code): deploy, shot, smoke, expose.

## Mocked or not live
- WhatsApp: the Meta Cloud API token (test number +1 555 188 5173, Meta test WABA) was configured on 6 Nov 2026 at 20:19Z. Test messages were sent only to the team's own phone (the owner number in demos is a team member's own, with consent); Meta delivery callbacks are stored in `data/wa_status.jsonl`. Free-form and button messages only deliver inside Meta's 24 hour customer-service window (the owner's phone must message the test number first); templates deliver at any time. The Finnish utility template `kaiku_hours_fi` (three quick-reply buttons) was submitted on 6 Nov 20:28Z and is pending Meta approval; the code path is behind `WA_TEMPLATE_NAME` and off until approval (`docs/whatsapp.md`). Without a working WhatsApp send the contact step produces the decision link instead. Client unit tests use a fake transport; live-sending tests run only with `KAIKU_LIVE=1`.
- Call lane (ElevenLabs outbound Finnish call): on main (`kaiku/contact/call.py`): ElevenLabs Conversational AI agent created, phone number present on the existing account, decision webhook `/webhooks/call`. The outbound call is NOT yet working: the latest attempt (6 Nov 20:23Z, `data/call_log.jsonl`) failed with `dial failed with 488 Not Acceptable Here (SIP 488)` through the ElevenLabs SIP trunk to Zadarma, after earlier 422/400 attempts, so no call has reached a phone. The WhatsApp step escalates to the call after `WA_ESCALATE_AFTER_S` seconds (default 120, the demo config sets 600). The WhatsApp or decision-link rung is what the demo relies on.
- Google signal (Serper): `SERPER_API_KEY` is set and `google_now` (`kaiku/detect/signals.py`) calls Serper places, but the demo business is fictional, so it returns no hours and the status is unknown.
- Security: the public events feed and suggestion endpoints do not carry the owner's decision link unless the viewer holds the demo key (cookie set by `?key=`, or `X-Kaiku-Key` header). httpx request logging is off so API keys never reach the journal. The demo reset also clears pending MCP proposals. Delivery statuses are logged.
- Peer priors (`data/peer_priors.json`) are hand-made; website parsing is tested on a mocked page.
- Yext sandbox has no publisher listings: the write is real, the syndication to Google and others is not.
- Room answers on `/map` are demo data and are not written to Yext.

## Fictional data
"Furry Paw Vet Clinic" is Fonecta's sandbox business; its history is a labelled sample we wrote.

## GenAI in the product
Claude claude-sonnet-5-5: the voice tool loop and the Aura subscription proposals. ElevenLabs: speech to text (scribe_v1) and text to speech. The suggestion engine and its Finnish messages are rules and templates, not a model.

## Data sources and licences
See docs/DATA_SOURCES.md.
