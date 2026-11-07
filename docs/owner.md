# Owner home (`/`, `/owner`)

The owner home. Template `owner.html`; scripts `app.js`, `owner.js`, `listing.js`, `chat.js`; styles `horizon.css`, `owner.css`, `chat.css`.

Kept as it was: status chips and the small "i" toggle, keyed Reset footer (key holder only), the voice orb (its transcript goes into the chat).

Layout (v3, owner's three edits, 7 Nov): hero, then SUGGESTIONS full width (3 per row at 1440), then a row with the chat (wider) and ON FONECTA NOW, then the Reset footer. At 390 the same order, stacked.

| Widget | Shows | Data |
|---|---|---|
| Hero (`#hero`) | headline "Furry Paw Vet Clinic: 3 things to fix before Christmas." (count = pending items, "nothing to fix" at zero), arc fill and sweeping dot = score/100, big number = the listing score, caption "NEEDS UPDATES · 3 OF 7 CHECKS" (live value on 7 Nov 2026, score 45) | `GET /api/score/furry-paw` (docs/score.md), polled every 10 s and after every decision |
| SUGGESTIONS (`#suggestions`) | one card per feed item. Pending cards have **Accept**, **Suggest a change** and a faint **Discard**. description and review cards show the proposed text in a quote block. "No change" notes have no actions | `GET /api/feed/furry-paw` |
| CHAT WITH KAIKU (`#chat`) | opens EMPTY: the faint contact line (when contact events exist, "EMAIL SENT 23:48 · WHATSAPP SENT 23:49") and the invitation "Nothing to type yet. Accept a suggestion above and I will talk you through it, or tell me what changed in your own words." with the mono sub-line "Text here, or hold space and talk". Input placeholder "Type, or hold space to talk". The voice orb feeds the same chat | `GET /api/chat/open` (this session's log only; `?full=1` = the old opening, kept for WhatsApp and the API), `POST /api/chat` |
| ON FONECTA NOW (`#listing`) | name, address, category, phone, website, regular hours, holiday rows, description, reviews, read time. Missing = warn "no data" (links to its card when one exists); a value a pending suggestion would change gets "Kaiku suggests ..." | `GET /api/listing/furry-paw` (`kaiku/listing/router.py`, Yext sandbox through the apply client, cached 30 s, `?fresh=1`) |

Card actions (`kaiku/chat/router.py`, the conversation itself in `kaiku/chat/flow.py`, see docs/chat.md for every text):
- `POST /api/suggestions/{id}/accept` applies at once (`actions.decide`, approve, via web): the Yext write and read-back, then Kaiku's receipt, the recurring question when last year's data exists, and the next item with its reason (tests/test_chat.py::test_accept_applies_at_once_then_recurring_then_next).
- `POST /api/suggestions/{id}/change` hands over too: "You want to change <title>. I suggested <hours> because <reason>. What should it be?" then the owner's value, "<value> on 24.12., shall I save it?", then "yes".
- `POST /api/suggestions/{id}/discard` is `decide(..., "decline", via="web")` (a learn event is emitted), the card flips to declined and fades, and Kaiku writes one line ("Okay, I leave Christmas Eve 24.12. as it is.").

Wiring: `kaiku/app.py` must include the `score` and `listing` routers (module list). Files: `owner.js` (hero, cards), `listing.js`, `chat.js`, `owner.css`. Components talk through window events (`kaiku:feed`, `kaiku:accept`, `kaiku:change`, `kaiku:sysline`, `kaiku:refresh`).

Status: the engine builds every card `proposed`. `kaiku.chat.feed.with_decisions` lays the owner's recorded decisions over a copy (approved = approved, edited or applied; declined), used by the chat, by `/api/feed` (after its cache) and so by the cards.

The feed's network build takes seconds (one HTTP signal per holiday), so the chat and the cards paint first from `network=0` and then upgrade; a slow build is cached for 30 s.

Demo drawer (holiday picker, Run the chain, time travel, Reset): `/owner/drawer`, key holders only, opened by `?key=...#drawer`. The live events strip is on `/judge?key=...` only.

## Demo contact

At the Joki Q&A a visitor may want the email, the WhatsApp message and the call on their own device. The keyed drawer has a "Demo contact" box (Email, Phone in international format, Save, "Back to my own"). It posts to `POST /api/demo/contact` (key as `X-Kaiku-Key` or `?key=`; `GET` returns the masked values, `DELETE` or empty fields clear). The override lives in `data/demo_contact.json` (gitignored) and beats `OWNER_EMAIL` / `OWNER_WHATSAPP` / the business record for the email step, the WhatsApp step, the call and the WhatsApp receipt; an inbound WhatsApp from that phone is handled exactly like the owner's. Validation: email needs `@` and a dot, phone is `+` and 8 to 15 digits (400 otherwise). Events and logs carry masks only (`e***@fonecta.fi`, `+358***123`). `POST /api/reset` keeps the override; `?contact=1` clears it. WhatsApp reaches only numbers registered in the Meta test app (SMS code, max 5); email and the call reach any address or number. Ask the person first, clear it after.

## Console

- `GET /console?key=<key>` (same key rule as `/judge`, 403 without it) is one phone-width page for the Q&A table: `kaiku/console/router.py`, `templates/console.html`, `static/console.js`.
- "Who Kaiku reaches": the demo contact box (Save, Back to my own, masked state) on `/api/demo/contact`, the WhatsApp note, and the last call line from `data/call_log.jsonl` (time and ok or reason only).
- "The customer we were given": Furry Paw Vet Clinic, the score line from `/api/score/furry-paw?quick=1` and the ON FONECTA NOW panel (`listing.js`, `/api/listing/furry-paw`).
- "Run it": Run the chain (24.12.) on `/api/run` and Reset demo on `/api/reset` (the demo contact stays), the 'moi' reminder for the 24 h WhatsApp window, and a link to `/judge?key=...` built in the browser.
- No full phone or email is ever in the HTML (tests/test_console.py); the page stays silent on test servers like every other page.
