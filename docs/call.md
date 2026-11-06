# Call lane (contact ladder step 2)
Flow: WhatsApp first. If no decision arrives within `WA_ESCALATE_AFTER_S` (or WhatsApp fails), `ladder._call_step` calls `kaiku.contact.call.place_call(suggestion)`. Kaiku phones the owner (demo: `OWNER_WHATSAPP`, Dayo's own number) from an ElevenLabs number, explains the proposal, asks "Hyväksytkö?". When the call ends ElevenLabs posts the transcript to `PUBLIC_URL/webhooks/call` (`call_router.py`), which derives a Decision with `via: "call"`, marks it decided in the WhatsApp context store (so a late WhatsApp tap is ignored), emits "Puhelu: ..." events, and hands it to `chain.on_decision` (which calls `decide.resolve`). Same path as a WhatsApp tap.

Files: `kaiku/contact/call.py` (setup, place_call, CLI), `kaiku/contact/call_router.py` (webhook, parsers), `tests/test_call.py` (29 tests, fake transport), `data/sample_suggestion.json` (CLI sample, fictional). Call log: `data/call_log.jsonl` (suggestion id, conversation id, last 4 digits of the number; no keys).

## Endpoints used (base https://api.elevenlabs.io, header xi-api-key)
| Call | Endpoint | Status |
|---|---|---|
| create agent | POST /v1/convai/agents/create | documented |
| list numbers | GET /v1/convai/phone-numbers | documented |
| outbound call | POST /v1/convai/twilio/outbound-call {agent_id, agent_phone_number_id, to_number, conversation_initiation_client_data{dynamic_variables,user_id}, telephony_call_config} -> {success, conversation_id, callSid} | documented (fetched) |
| workspace webhook | POST /v1/workspace/webhooks {settings{auth_type:"hmac",name,webhook_url}} -> {webhook_id, webhook_secret} | ASSUMED from memory |
| set post-call webhook | PATCH /v1/convai/settings {webhooks{post_call_webhook_id, events:["transcript"]}} | ASSUMED, best effort |
| search / buy native number | GET /v1/convai/phone-numbers/available?country=US, POST /v1/convai/phone-numbers/purchase | ASSUMED. The public docs list no native purchase API (only Twilio, SIP trunk, other providers). On 404/405 setup stops and says to buy a number in the dashboard (Agents > Phone numbers) or import a Twilio number, then rerun `setup` (it picks up any existing number). |
| webhook payload | `type: post_call_transcription`, `data.{conversation_id, transcript[{role,message}], analysis.data_collection_results, conversation_initiation_client_data.dynamic_variables}`; `call_initiation_failure` with `failure_reason` | documented |
| webhook signature | header `ElevenLabs-Signature: t=<unix>,v0=<hex>`, HMAC-SHA256 over `"<t>.<raw body>"`, 30 min tolerance | ASSUMED (docs only say "use the SDK") |
The outbound endpoint is the Twilio one in the docs; for a native ElevenLabs number it is assumed to accept the native `agent_phone_number_id` too. If it answers 4xx, check the current outbound docs for the native-number variant (the SIP trunk variant is `/v1/convai/sip-trunk/outbound-call`).

Number purchase guard: a number is bought only when its monthly price is known and under 10 (any currency); unknown or higher price stops with the price in the report.

## Decision capture
Agent has `data_collection` fields `action` (approve|edit|decline|none) and `hours` (`HH:MM-HH:MM` or `closed`). The webhook uses them first; if absent it parses the transcript: only owner turns after the agent's "Hyväksytkö" question, last decisive turn wins. Parser: kyllä/joo/hyväksyn/sopii = approve; ei/ei kiitos/en = decline; "9-13", "klo 8.30-12", "yhdeksästä yhteen" (end below 12 means afternoon: 13), "kymmenestä kahteen", "suljettu/kiinni" = edit. No decision found: event "Puhelu: päätöstä ei saatu", nothing resolved (the decide step times out as usual). A call that was never answered emits "Puhelu: omistaja ei vastannut".

## Script (English gloss)
First message: "Hei, täällä Kaiku, Fonecta Connectin avustaja. Soitan yrityksenne aukioloajoista, onko hetki aikaa?" (Hello, this is Kaiku, Fonecta Connect's assistant. I am calling about your opening hours, do you have a moment?)
Then, per call via dynamic variables `business_name, holiday_name_fi, holiday_date_fi (24.12.), proposed_hours (9-13), last_year, reason` (+ `suggestion_id, business_id`):
1. Two sentences: "{holiday} on {date} ja ehdotan aukioloajaksi {hours}, koska {reason}." (The holiday is on {date} and I suggest opening hours {hours}, because {reason}.)
2. "Hyväksytkö?" (Do you approve?)
3. Yes: "Kiitos, päivitän tiedot nyt. Näkyy pian Googlessa ja muissa kanavissa." (Thank you, I am updating the details now. It will soon show in Google and other channels.) then ends the call.
4. Other hours: repeats them back, "Oliko oikein?" (Was that right?), thanks, ends.
5. No: "Selvä, en muuta mitään. Kiitos ajastasi." (Understood, I change nothing. Thank you for your time.) ends.
6. Anything else: answers only from the given facts, else says it does not know and asks "Hyväksytkö?" again. Never invents facts, never asks for personal data. Max call 240 s, ringing timeout 30 s.
The agent uses model eleven_flash_v2_5, LLM gemini-2.0-flash (from the earlier payload draft; the field is a guess, change in `agent_payload()` if rejected), language `fi`, voice `ELEVENLABS_VOICE_ID`.

## Run
Needs the unrestricted key in `.env` (ELEVENLABS_API_KEY) and PUBLIC_URL reachable from the internet.
- `cd /root/hack/kaiku && .venv/bin/python -m kaiku.contact.call setup` creates webhook, agent, number and stores ELEVENLABS_WEBHOOK_ID/SECRET, ELEVENLABS_AGENT_ID, ELEVENLABS_PHONE_NUMBER_ID in `.env`; prints ids only. Restart the service afterwards so the running app sees the secret.
- `... call status` shows which settings exist (booleans only).
- `... call call --to +358451291684 --suggestion data/sample_suggestion.json` places a live test call.
Caller id will be a US number. Cost: ElevenLabs agent minutes (about a minute per call) plus the number's monthly fee if any; a demo costs cents. Not run live yet.
