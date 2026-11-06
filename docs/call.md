# Call lane (contact ladder step 2)
Status (6 Nov 2026): The outbound call works: on 6 Nov 2026 at 21:24Z (`data/call_log.jsonl`) a call was answered by the team's own phone, the Kaiku Finnish agent spoke its opening line ("Hei, täällä Kaiku, Fonecta Connectin avustaja..."), the call lasted 37 s, and the ElevenLabs post-call webhook reached `POST /webhooks/call` (HTTP 200). The earlier SIP 488 (20:12Z and 20:23Z) was caused by the Zadarma SIP trunk rejecting offers with media encryption; the ElevenLabs trunk setting for media encryption was changed from "allowed" to "disabled" on 6 Nov 2026 at about 21:21Z (a dashboard edit, no code change for that part). Later dials at 21:27Z (SIP 408 Ringing Timeout) and 21:31Z (SIP 480 Temporarily Unavailable) were simply not answered. Not yet exercised end to end: a call in which the owner says "Hyväksyn", so that the post-call webhook creates a Decision with via "call" and the apply step writes Yext. The WhatsApp path has been proven end to end with a real Yext write at 20:42Z. Calls were made only to the team's own phone.

Flow: WhatsApp first. If no decision arrives within `WA_ESCALATE_AFTER_S` (or WhatsApp fails), `ladder._call_step` calls `kaiku.contact.call.place_call(suggestion)`. Kaiku phones the owner (demo: `OWNER_WHATSAPP`, Dayo's own number) from an ElevenLabs SIP trunk number (Zadarma, caller ID is the team member's own number), explains the proposal, asks "Hyväksytkö?". When the call ends ElevenLabs posts the transcript to `PUBLIC_URL/webhooks/call` (`call_router.py`), which derives a Decision with `via: "call"`, marks it decided in the WhatsApp context store (so a late WhatsApp tap is ignored), emits "Puhelu: ..." events, and hands it to `chain.on_decision` (which calls `decide.resolve`). Same path as a WhatsApp tap.

Files: `kaiku/contact/call.py` (setup, place_call, CLI), `kaiku/contact/call_router.py` (webhook, parsers), `tests/test_call.py` (29 tests, fake transport), `data/sample_suggestion.json` (CLI sample, fictional). Call log: `data/call_log.jsonl` (suggestion id, conversation id, last 4 digits of the number; no keys).

## Endpoints used (base https://api.elevenlabs.io, header xi-api-key)
| Call | Endpoint | Status |
|---|---|---|
| create agent | POST /v1/convai/agents/create | documented |
| list numbers | GET /v1/convai/phone-numbers | documented |
| outbound call | POST /v1/convai/sip-trunk/outbound-call (used because `ELEVENLABS_PHONE_PROVIDER=sip_trunk`; the Twilio variant `/v1/convai/twilio/outbound-call` is not used)  {agent_id, agent_phone_number_id, to_number, conversation_initiation_client_data{dynamic_variables,user_id}, telephony_call_config} -> {success, conversation_id, callSid} | documented (fetched); request read timeout 75 s, `ringing_timeout_secs` 45 |
| workspace webhook | POST /v1/workspace/webhooks {settings{auth_type:"hmac",name,webhook_url}} -> {webhook_id, webhook_secret} | ASSUMED from memory |
| set post-call webhook | PATCH /v1/convai/settings {webhooks{post_call_webhook_id, events:["transcript"]}} | ASSUMED, best effort |
| search / buy native number | GET /v1/convai/phone-numbers/available?country=US, POST /v1/convai/phone-numbers/purchase | ASSUMED. The public docs list no native purchase API (only Twilio, SIP trunk, other providers). On 404/405 setup stops and says to buy a number in the dashboard (Agents > Phone numbers) or import a Twilio number, then rerun `setup` (it picks up any existing number). |
| webhook payload | `type: post_call_transcription`, `data.{conversation_id, transcript[{role,message}], analysis.data_collection_results, conversation_initiation_client_data.dynamic_variables}`; `call_initiation_failure` with `failure_reason` | documented |
| webhook signature | header `ElevenLabs-Signature: t=<unix>,v0=<hex>`, HMAC-SHA256 over `"<t>.<raw body>"`, 30 min tolerance | ASSUMED (docs only say "use the SDK") |
The number is a SIP trunk (provider `sip_trunk`), so the call goes to `/v1/convai/sip-trunk/outbound-call`; no Twilio number is used. The trunk's media encryption setting must be "disabled" for Zadarma.

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
6. Anything else: answers only from the given facts, else says it does not know and asks "Hyväksytkö?" again. Never invents facts, never asks for personal data. Max call 240 s, ringing timeout 45 s.
The agent uses model eleven_flash_v2_5, LLM gemini-2.0-flash with a Finnish system prompt, language `fi`, voice `ELEVENLABS_VOICE_ID`.

## Run
Needs the unrestricted key in `.env` (ELEVENLABS_API_KEY) and PUBLIC_URL reachable from the internet.
- `cd /root/hack/kaiku && .venv/bin/python -m kaiku.contact.call setup` creates webhook, agent, number and stores ELEVENLABS_WEBHOOK_ID/SECRET, ELEVENLABS_AGENT_ID, ELEVENLABS_PHONE_NUMBER_ID in `.env`; prints ids only. Restart the service afterwards so the running app sees the secret.
- `... call status` shows which settings exist (booleans only).
- `... call call --to +358451291684 --suggestion data/sample_suggestion.json` places a live test call.
Caller ID is the team member's own number (Zadarma SIP trunk). Cost: ElevenLabs agent minutes (about a minute per call) plus the number's monthly fee if any; a demo costs cents.
