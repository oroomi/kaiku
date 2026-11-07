# Owner home (`/`, `/owner`)

The owner home. Template `owner.html`; scripts `app.js`, `owner.js`, `listing.js`, `chat.js`; styles `horizon.css`, `owner.css`, `chat.css`.

Kept as it was: status chips and the small "i" toggle, keyed Reset footer (key holder only), the voice orb (its transcript goes into the chat).

Layout (v3, owner's three edits, 7 Nov): hero, then SUGGESTIONS full width (3 per row at 1440), then a row with the chat (wider) and ON FONECTA NOW, then the Reset footer. At 390 the same order, stacked.

| Widget | Shows | Data |
|---|---|---|
| Hero (`#hero`) | headline "Furry Paw Vet Clinic: 3 things to fix before Christmas." (count = pending items, "nothing to fix" at zero), arc fill and sweeping dot = score/100, big number = the listing score, caption "NEEDS UPDATES · 4 OF 7 CHECKS" | `GET /api/score/furry-paw` (docs/score.md), polled every 10 s and after every decision |
| SUGGESTIONS (`#suggestions`) | one card per feed item. Pending cards have **Accept** and **Suggest a change**. description and review cards show the proposed text in a quote block. "No change" notes have no actions | `GET /api/feed/furry-paw` |
| CHAT WITH KAIKU (`#chat`) | Kaiku's opening, one input. Contact events appear as one faint mono system line after the intro ("EMAIL SENT 23:48 · WHATSAPP SENT 23:49"; degraded sends are not shown) | `GET /api/chat/open`, `POST /api/chat`, contact events |
| ON FONECTA NOW (`#listing`) | name, address, category, phone, website, regular hours, holiday rows, description, reviews, read time. Missing = warn "no data" (links to its card when one exists); a value a pending suggestion would change gets "Kaiku suggests ..." | `GET /api/listing/furry-paw` (`kaiku/listing/router.py`, Yext sandbox through the apply client, cached 30 s, `?fresh=1`) |

Card actions (`kaiku/chat/router.py`):
- `POST /api/suggestions/{id}/accept` `{business_id, session}` calls `kaiku.chat.actions.decide(..., "approve", via="web")`, the chat's own path. The reply (confirmation plus standing-permission question) goes into the chat session, so the next "yes" answers the question.
- `POST /api/suggestions/{id}/change` sets that suggestion as the session focus and logs Kaiku's line "You want to change <title>. Tell me the new hours, or what is wrong, by text or by holding space to talk." The next message ("make it 10-14", "closed") is decided against it.

Wiring: `kaiku/app.py` must include the `score` and `listing` routers (module list). Files: `owner.js` (hero, cards), `listing.js`, `chat.js`, `owner.css`. Components talk through window events (`kaiku:feed`, `kaiku:accept`, `kaiku:change`, `kaiku:sysline`, `kaiku:refresh`).

Status: the engine builds every card `proposed`. `kaiku.chat.feed.with_decisions` lays the owner's recorded decisions over a copy (approved = approved, edited or applied; declined), used by the chat, by `/api/feed` (after its cache) and so by the cards.

The feed's network build takes seconds (one HTTP signal per holiday), so the chat and the cards paint first from `network=0` and then upgrade; a slow build is cached for 30 s.

Demo drawer (holiday picker, Run the chain, time travel, Reset): `/owner/drawer`, key holders only, opened by `?key=...#drawer`. The live events strip is on `/judge?key=...` only.
