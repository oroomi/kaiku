# Owner home (`/`, `/owner`)

The home page is the original Kaiku home with four widgets replaced (owner's edits, 6 Nov). Template `owner.html`, scripts `app.js` (status chips, keyed reset, header date), `owner.js` (hero, suggestions, thread), `chat.js` (chat widget, keyed drawer), styles `horizon.css` + `owner.css` + `chat.css`.

Kept as it was: status chips, hero (headline, arc with the sweeping dot, Connect vs Kaiku, cap), keyed Reset footer (shown only to the key holder). The voice orb stays; its transcript goes into the chat.

| Widget | Shows | Data |
|---|---|---|
| Hero | the lead suggestion as one sentence, arc dot at its confidence, before/after hours | `GET /api/feed/furry-paw`, `GET /api/business/furry-paw`, step count from events |
| CHAT WITH KAIKU (`#chat`) | Kaiku's opening (intro, one bubble per suggestion, the no_change note), one input, Enter sends. No buttons, no quick replies | `GET /api/chat/open` (first call `?quick=1`, no network signals), `POST /api/chat` |
| MESSAGE TO THE OWNER (`#thread`) | thread of Kaiku messages and owner answers, labelled EMAIL / WHATSAPP / CALL / WEB, newest last. "Nothing sent yet." when empty | contact, decide and apply events for the business (`/api/events/recent` then SSE `/api/events`), plus the web chat messages (kept in sessionStorage `kaikuWeb`) |
| SUGGESTIONS FOR ... (`#suggestions`) | one card per feed item, any kind: title, text, hours chip or "no change", confidence, reason sources, status chip proposed / approved / declined | `GET /api/feed/furry-paw`, polled every 10 s and refreshed on suggest/decide/apply/learn events and after each chat reply |

Thread text keys read from an event's `detail`: contact `message_en | message | text | body` (else the English title), decide `answer | reply | text | message` (else title), apply `receipt | message_en | text`. Channel from `detail.channel`, decide `via`, else the event title. Contact events marked `degraded` (nothing left the building) are not shown. A chat-made decision is not duplicated: the owner's WEB message already stands for it.

Status: the engine builds every card `proposed`. `kaiku.chat.feed.with_decisions` lays the owner's recorded decisions over a copy (approved = approved, edited or applied; declined), used by the chat, by `/api/feed` (after its cache) and so by the cards.

The feed's network build takes seconds (one HTTP signal per holiday), so the chat and the cards paint first from `network=0` and then upgrade; a slow build is cached for 30 s.

Demo drawer (holiday picker, Run the chain, time travel, Reset): `/owner/drawer`, key holders only, opened by `?key=...#drawer`. The live events strip is on `/judge?key=...` only.
