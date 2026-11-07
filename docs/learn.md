# learn (task 8)
Learns per business from decisions and owns the chain's clock. EN glosses in brackets.

**Learned** (data/learn_prefs.json, atomic write; dir = env KAIKU_DATA_DIR, default <repo>/data):
- edit: hours stored per holiday id (`jouluaatto`) and holiday+weekday (`jouluaatto|thu`).
- decline: count + reason chips per holiday id. standing_permission: scope `holiday` (same holiday) or `all`, plus grant date.

**Rules in apply_prefs** (returns a new dict):
- edit exists: proposed = edited hours, confidence = max(old, 0.9), reason_fi gains "Viime vuonna muokkasit tämän ajaksi 10-14" [Last year you edited this to 10-14].
- declined 2+ times: kind no_change, "Olet hylännyt tämän ehdotuksen kahdesti" [You declined twice]; declined once: confidence -0.15 (gate may make it an ask).
- standing permission covers it: auto_apply true + auto_apply_reason_fi "Annoit pysyvän luvan (24.12.2026), joten päivitämme tämän puolestasi".

Holiday id comes from suggestion.holiday_id, suggestion.holiday.name_fi (slugged, ä>a) or "md-MM-DD".
Each learned decision emits a step "learn" Event if kaiku.events is importable.

**Clock rule**: only `kaiku.learn.timetravel.today()` / `now()` may be used by the chain. Fake date lives in data/timetravel.json so web app, CLI and voice agree. `/api/timetravel?date=YYYY-MM-DD` sets, `date=real` or empty clears.

**Demo**: set today = 2026-12-17 and the chain detects jouluaatto 24.12.; set today = 2026-11-02 and it detects isänpäivä 8.11. (not a public holiday: "no change" is shown as reliability).

API: GET/POST /api/timetravel, GET /api/learn/prefs/{business_id}, POST /api/learn/decision {business_id, suggestion, decision}.

## Contact channel preference (7 Nov)

`prefs.get_contact_channel(business_id)` / `prefs.set_contact_channel(business_id, channel, said)`; channel is `email`,
`whatsapp` or `call` (None until the owner answers). It lives in `learn_prefs.json` next to edits, declines and standing
permission, so the same reset (`/api/reset?learn=1`) clears it. Setting it emits a learn event, for example "Learned:
prefers WhatsApp next time", with the owner's own words in `detail.said`. `prefs.parse_channel(text)` reads a typed answer.

Where it is asked: at the end of the WhatsApp / web chat conversation (`kaiku/chat/flow.py`, stage `channel`) and under the
receipt on the email decision page (`POST /api/decide/{token}/channel`, same token, allowed once the decision is in).

What the ladder does with it (`kaiku/contact/ladder.py`, `contact`): email or no answer = today's order (email, then
WhatsApp after `EMAIL_ESCALATE_AFTER_S`, then the call). `whatsapp` = WhatsApp first, then email, then the call. `call` = the
call first, then WhatsApp, then email. The first rung logs "Reaching the owner by WhatsApp first (their preference)" (or by
call). A preference never bypasses the outbound safety: WhatsApp and email go through the guarded clients and the call rung
is `call.place_call`, which still obeys `KAIKU_NO_CALL` and `outbound_allowed`.

## Standing permission in the chain (7 Nov)
When a standing permission covers a holiday, `apply_prefs` sets `auto_apply`; `kaiku/chain.py` then skips the contact and decide waits, applies the decision (`reason_chip: standing`), and sends the owner one WhatsApp line afterwards ("Under your standing permission I set ... everywhere Connect publishes. Reply with other hours if you want it changed."). Test: `tests/test_core.py::test_standing_permission_applies_without_asking`.
