# Cold start: a customer with no history

Slide 8: "how it behaves for a customer with no history". Kaiku does not guess hours it has no evidence for: it asks one question and proposes nothing. Checked on 7 Nov 2026 against `kaiku/suggest/engine.py` (`ASK_BELOW = 0.6`), `kaiku/suggest/explain.py` and `python -m kaiku.suggest.backtest data/sample_cases.json` (cases 4, 5, 7, 8 are cold start).

## What the engine does
No last-year exception and no website hours: only two rules remain (see [suggest.md](suggest.md)).
1. A public holiday where the whole category is closed (St. Stephen's Day, Midsummer Eve for shops, and so on): propose "closed" at confidence 0.65 and say the proposal rests on similar businesses (backtest cases 5 and 7).
2. Anything else (a short-hours prior, or a day that is not a public holiday): confidence 0.50, below 0.6, so Kaiku asks one question and proposes nothing (backtest cases 4 and 8).
Nothing in the cold start can exceed 0.65, and nothing above 0.6 is a guess about hours. A prior of "regular" gives `no_change` (0.70, case 10).

## The question the customer receives (English)
> Hi Furry Paw Vet Clinic! Christmas Eve is on Thursday 24.12. We do not have reliable data on your hours. Are you open on Christmas Eve 24.12.? Reply for example 9-13 or closed.

On WhatsApp it goes with two buttons, **Tell my hours** and **No thanks** (`ladder.buttons_for`, kind `ask`). Free text such as "9-13" or "closed" becomes an edit decision; the receipt, the write to Yext and the read-back are the same as for any approved suggestion. Finnish owners get the same question in Finnish (`ask_text_fi`; text in [final_messages.md](final_messages.md) section 9). The text above is the engine's output for the demo clinic with its history removed (`kaiku.contact.messages._engine_cases`, key `ask`).

## The room flow
`/room` shows a QR code and `/join` makes the visitor the owner of one real Turku business from OpenStreetMap, which has no holiday history. The page asks "Are you open on Christmas Eve, 24 Dec?" (chips or free text, at most 40 characters; `kaiku/web/templates/join.html`, `kaiku/map/router.py`). Answers turn the dot green on `/map`. These answers are demo data and are not written to Yext. Businesses whose OSM text mentions 24 Dec (2 of 813) are never given to visitors.

## After the first answer
The answer is stored as a preference for that holiday, so next year it is a proposal at confidence at least 0.9, not a question ([learn.md](learn.md); `kaiku/learn/prefs.py`, `EDIT_CONF = 0.9`, `tests/test_learn.py::test_edit_then_next_cycle_proposes_edited`).

## Where the cold-start signal comes from in production
Category peers: Connect's own customer base, the share of similar businesses that changed hours on each holiday. Today it is hand-made priors in `data/peer_priors.json`, labelled as such, because we have no Fonecta data. See [DATA_SOURCES.md](DATA_SOURCES.md) source 5.
