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
