# Contact step (WhatsApp first, then a call)

Step 3 of the chain. The owner is reached without a login; the message explains why, and one tap decides.

## The ladder
1. WhatsApp message with three reply buttons: **Hyväksy / Muokkaa / Ei kiitos** (kind `ask`: **Kerron aikani / Ei kiitos**; kind `no_change`: plain reassurance, no buttons).
2. (Call lane: `kaiku/contact/call.py` is on main but the outbound call does not connect yet, SIP 488.) If there is no decision after `WA_ESCALATE_AFTER_S` (demo 120 s, production 24 h, the length of the WhatsApp window), `kaiku.contact.call.place_call(suggestion)` places a Finnish call. If the call lane is not configured the ladder logs `call lane not configured` in `channel_log`.
3. No email, by decision.

Entry point: `kaiku.contact.ladder.contact(suggestion)`, registered as `kaiku.chain.register("contact", contact)` when core exists. Every send appends to `suggestion["channel_log"]` and emits a `contact` event. Demo rule: the recipient is always `OWNER_WHATSAPP` from `.env` (Dayo's own phone).

## The 24 h window rule
Free-form messages (text, buttons) can only be sent within 24 h after the customer last wrote to us. Outside it Graph API returns error 131047 and the client returns `{"needs_template": True}`. The ladder then sends the template `hello_world` (the only template a test number has), stores the real message as `pending_buttons` in `data/wa_context.json`, and delivers the buttons as soon as the owner replies to the template. A real production setup would use an approved Finnish utility template with the three quick-reply buttons instead.

## Inbound -> Decision
`POST /webhooks/whatsapp` turns a reply into `{suggestion_id, action, edited, reason_chip, standing_permission, via:"whatsapp", at}`, emits `Event(step="decide")` and calls `kaiku.chain.on_decision(decision)` (both guarded imports).
- Button ids are `approve:<suggestion_id>` etc., so even a stale context resolves; plain `approve` falls back to `context.id` -> `data/wa_context.json` message map, then the phone's latest suggestion.
- **Muokkaa** does not make a Decision by itself: it sends the edit prompt and waits; the next free text becomes the `edit` Decision.
- Free text: `9-13`, `9:00-13:00`, `klo 10-15` -> edit; `suljettu`/`kiinni` -> edit with `"closed"`; `ei` -> decline; `ok`/`kyllä`/`jees` -> approve; anything else -> a short "did not understand" reply.
- Webhook redeliveries are deduplicated by message id; a suggestion decides once.
- Status callbacks (sent/delivered/read/failed) are parsed and returned, no Decision.
- If `WA_APP_SECRET` is set, `X-Hub-Signature-256` is verified.
- The receipt after apply: `router.send_receipt(phone, apply_result)`; apply passes an ApplyResult optionally enriched with `holiday_name_fi` and `hours`.

## Webhook setup
1. Run `python -m kaiku.contact.cli init` (puts `WA_VERIFY_TOKEN` in `.env` if absent).
2. Meta developer console > WhatsApp > Configuration > Webhook: Callback URL = `PUBLIC_URL/webhooks/whatsapp`, Verify token = value of `WA_VERIFY_TOKEN`; click Verify.
3. Subscribe to the `messages` field.
4. Add Dayo's number under API Setup > To and confirm the OTP (error 131030 otherwise).
5. `python -m kaiku.contact.cli send-test` sends the Furry Paw message with buttons to `OWNER_WHATSAPP`.

## Files
`messages.py` (Finnish texts + `docs/final_messages.md` export), `whatsapp.py` (Graph v21.0 client, injectable transport, `data/wa_sends.jsonl` log without token), `router.py`, `ladder.py`, `cli.py`. Env: `WA_TOKEN, WA_PHONE_ID, WA_WABA_ID, WA_VERIFY_TOKEN, OWNER_WHATSAPP, WA_ESCALATE_AFTER_S, WA_APP_SECRET`.

## What did not work / limits
- Not yet run against the real Graph API: when this was built the Meta test number did not exist, so everything is tested with a fake transport and Meta's documented payload shapes. The live test self-skips without `WA_TOKEN`.
- Test-number access tokens last 24 h; a system-user token is needed for the weekend.
- A test number can only message numbers on its allowed list (131030).
- `hello_world` is English; a Finnish template needs Meta approval, so for the demo the first contact uses it only to open the window.

## Message source and register
- When the Suggestion carries `message_fi`/`message_en` (suggest engine), the lane sends the engine's text verbatim (its holiday name and last-year hours) plus the decide line; the generic text is a fallback that states no fact it was not given.
- Register is the polite plural throughout (te, teidän: "olette suljettuna", "aukioloaikanne"). When `decide_url` is set, a line "Voitte myös päättää selaimessa: <url>" is added (gloss: You can also decide in the browser).
- A button tap for an unknown suggestion id logs a warning, replies "En löytänyt ehdotusta, johon tämä vastaus liittyy." (gloss: I could not find the suggestion this reply belongs to.) and emits no Decision.
