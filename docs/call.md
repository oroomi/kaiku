# Call lane (contact ladder step 2)
Status (6 Nov 2026): The outbound call works: on 6 Nov 2026 at 21:24Z (`data/call_log.jsonl`) a call was answered by the team's own phone, the Kaiku agent (then still Finnish) spoke its opening line ("Hei, täällä Kaiku, Fonecta Connectin avustaja..."), the call lasted 37 s, and the ElevenLabs post-call webhook reached `POST /webhooks/call` (HTTP 200). The earlier SIP 488 (20:12Z and 20:23Z) was caused by the Zadarma SIP trunk rejecting offers with media encryption; the ElevenLabs trunk setting for media encryption was changed from "allowed" to "disabled" on 6 Nov 2026 at about 21:21Z (a dashboard edit, no code change for that part). Later dials at 21:27Z (SIP 408 Ringing Timeout) and 21:31Z (SIP 480 Temporarily Unavailable) were simply not answered. Proven end to end on 6 Nov 2026: at 21:46:53Z (`data/call_log.jsonl`, suggestion `6f1bd3dfdf`, business furry-paw, conversation `conv_8001m6sd85c3eqya7a17c1wkgmwk`) Kaiku phoned the team's own phone in English, the owner approved on the call, the post-call webhook created the Decision (via "call"), and Yext received 24.12. 9-13, read back and verified. The agent is English (language en) and, since 7 Nov, warm and joke-friendly: the first message is "Hi there! I'm Kaiku, an assistant from Fonecta, and I've got a few questions about your opening hours. Are you down for a quick chat?" (`FIRST_MESSAGE` in `call.py`). The call escalates after `WA_ESCALATE_AFTER_S` seconds (default 120; the live config sets 600). The WhatsApp path has been proven end to end with a real Yext write at 20:42Z. Calls were made only to the team's own phone.

Flow: the call is the third rung after email and WhatsApp (an owner who said "call" at the closing question gets it first). If no decision arrives within `WA_ESCALATE_AFTER_S` (or WhatsApp fails), `ladder._call_step` calls `kaiku.contact.call.place_call(suggestion)`. Kaiku phones the owner in English (the demo default; Finnish per owner via `owner_language: fi`) (demo: `OWNER_WHATSAPP`, Dayo's own number) from an ElevenLabs SIP trunk number (Zadarma, caller ID is the team member's own number), explains the proposal, asks "Do you approve?". When the call ends ElevenLabs posts the transcript to `PUBLIC_URL/webhooks/call` (`call_router.py`), which derives a Decision with `via: "call"`, marks it decided in the WhatsApp context store (so a late WhatsApp tap is ignored), emits "Call: ..." / "Puhelu: ..." events, and hands it to `chain.on_decision` (which calls `decide.resolve`). Same path as a WhatsApp tap.

Files: `kaiku/contact/call.py` (setup, place_call, CLI), `kaiku/contact/call_router.py` (webhook, parsers), `tests/test_call.py` (fake transport), `data/sample_suggestion.json` (CLI sample, fictional). Call log: `data/call_log.jsonl` (suggestion id, conversation id, last 4 digits of the number; no keys).

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
Agent has `data_collection` fields `action` (approve|edit|decline|none) and `hours` (`HH:MM-HH:MM` or `closed`). The webhook uses them first; if absent it parses the transcript: only owner turns after the agent's "Do you approve" / "Hyväksytkö" question, last decisive turn wins. English parser: yes/yeah/yep/sure/ok/okay/approve/"I approve" = approve; no/nope/no thanks = decline; "9-13", "9 to 1", "9am to 1pm", "nine to one", "ten to two", "closed" = edit (end below 12 without am/pm means afternoon). Finnish parser (still active): kyllä/joo/hyväksyn/sopii = approve; ei/ei kiitos/en = decline; "9-13", "klo 8.30-12", "yhdeksästä yhteen", "kymmenestä kahteen", "suljettu/kiinni" = edit. No decision found: event "Puhelu: päätöstä ei saatu", nothing resolved (the decide step times out as usual). A call that was never answered emits "Puhelu: omistaja ei vastannut".

## Script (English is the default; Finnish per owner)
The agent speaks English (`language: en`) for owners with `owner_language: en` (the demo default, set in `data/furry_paw.json`). The Finnish script is kept in `call.py` (`SYSTEM_PROMPT_FI`, `FIRST_MESSAGE_FI`, `DATA_COLLECTION_FI`) and used when `owner_language` is `fi` (`call.agent_config("fi")`, `python -m kaiku.contact.call update-agent --lang fi`).
First message: "Hi, this is Kaiku, the Fonecta Connect assistant. I'm calling about your opening hours, do you have a moment?"
Per call via dynamic variables `business_name, holiday_name (Christmas Eve), holiday_date (spoken: December 24), proposed_hours (spoken: 9 AM to 1 PM), last_year, reason` (+ `suggestion_id, business_id`). The reason comes from `reasons[0].text_en`. For Finnish owners the variables are `holiday_name_fi, holiday_date_fi (24.12.), proposed_hours (9-13), ...` with `reasons[0].text_fi`.
1. Two sentences: the holiday, the date, the proposed hours and the reason.
2. "Do you approve?"
3. Yes: "Lovely, I'm setting it now! We'll update your information everywhere within the hour." then ends the call.
4. Other hours: repeats them back, "Is that right?", thanks, ends.
5. No: "Understood, I won't change anything. Thanks for your time." ends.
6. Anything else: answers only from the given facts, else says it does not know and asks "Do you approve?" again. Never invents facts, never asks for personal data. Max call 240 s, ringing timeout 45 s.
7. Closing question (every call, once the decision is settled; owner's note 7 Nov): "Before I go, next time something like this comes up, would you prefer we contact you a different way, WhatsApp or email, or is a call fine?" The agent accepts WhatsApp, email, call or "this is fine", repeats the choice in one short sentence ("Got it, WhatsApp next time.") and says goodbye. Finnish has the same step.
Data collection (English descriptions): `action` approve/edit/decline/none, `hours` HH:MM-HH:MM or closed, `preferred_channel` whatsapp | email | call | none.

### Remembered channel
The post-call webhook maps `preferred_channel` through `learn.prefs.parse_channel` and stores it with `set_contact_channel(business_id, channel)`, the same store and learn event the WhatsApp and email paths use. `none`, empty or an unknown value stores nothing. The decision handling is unchanged; the transcript fallback ignores everything after the closing question so "a call is fine" is never read as a decline. `update-agent` also pushes `ELEVENLABS_VOICE_ID` from `.env` as the agent voice.
The agent's language model is gemini-2.0-flash (temperature 0.5, run by ElevenLabs), its voice is Aurora (`ELEVENLABS_VOICE_ID` in `.env`) and its speech model is `eleven_v4` for English and Finnish (`tools/agent_voice.py` sets the voice settings). Latest calls placed 7 Nov 10:18:34Z and 10:23:22Z (`data/call_log.jsonl` on the demo host).

The live agent was switched to English on 6 Nov 2026 with `python -m kaiku.contact.call update-agent` (PATCH `/v1/convai/agents/{id}`, then a GET that checks `language` and `first_message`); verified `language: en`, English first message, English prompt and data collection.

## Run
Needs the unrestricted key in `.env` (ELEVENLABS_API_KEY) and PUBLIC_URL reachable from the internet.
- `cd /root/hack/kaiku && .venv/bin/python -m kaiku.contact.call setup` creates webhook, agent, number and stores ELEVENLABS_WEBHOOK_ID/SECRET, ELEVENLABS_AGENT_ID, ELEVENLABS_PHONE_NUMBER_ID in `.env`; prints ids only. Restart the service afterwards so the running app sees the secret.
- `... call update-agent [--lang en|fi]` PATCHes the live agent (language, first message, prompt, placeholders, TTS model, data collection) and verifies it with a GET.
- `... call status` shows which settings exist (booleans only).
- `... call call --to <your phone, international format> --suggestion data/sample_suggestion.json` places a live test call.
Caller ID is the team member's own number (Zadarma SIP trunk). Cost: ElevenLabs agent minutes (about a minute per call) plus the number's monthly fee if any; a demo costs cents.
