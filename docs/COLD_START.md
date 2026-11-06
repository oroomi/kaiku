# Cold start: a customer with no history

Kaiku does not guess hours it has no evidence for.

## What the engine does
No last-year exception, no website hours: only two rules remain (see [suggest.md](suggest.md)).
1. Public holiday where the whole category is closed (Tapaninpäivä, juhannusaatto for shops, and so on): propose "closed" at confidence 0.65, and say the proposal rests on similar businesses.
2. Anything else (short-hours priors, non-public days with a prior): confidence 0.50, below `ASK_BELOW = 0.6`, so Kaiku asks one question and proposes nothing.
Nothing in the cold start can exceed 0.65, and nothing above 0.6 is a guess about hours. A prior of "regular" gives `no_change` (0.70).

## The question
> Hei Furry Paw Vet Clinic! Jouluaatto on torstaina 24.12. Meillä ei ole varmaa tietoa aukioloajoistanne. Oletteko auki jouluaattona 24.12.? Vastaa esimerkiksi 9-13 tai suljettu.

Gloss: Hi Furry Paw Vet Clinic! Christmas Eve is on Thursday 24.12. We do not have reliable data on your hours. Are you open on Christmas Eve 24.12.? Reply for example 9-13 or closed. Buttons: "Kerron aikani" (I will tell you my hours) and "Ei kiitos". Free text such as "9-13" or "suljettu" becomes an edit decision.

## The room flow
`/room` shows a QR code, `/join` makes the visitor the owner of one real Turku business from OpenStreetMap, which has no holiday history. The suggest engine runs cold start and asks "Oletteko auki jouluaattona 24.12.?" (chips or free text, at most 40 characters). Answers turn the dot green on `/map`. These answers are demo data and are not written to Yext. Businesses whose OSM text mentions 24 Dec (2 of 813) are never given to visitors.

## After the first answer
The answer is stored as a preference for that holiday, so next year it is a proposal at confidence at least 0.9, not a question ([learn.md](learn.md)).

## Where the cold-start signal comes from in production
Category peers: Connect's own customer base, the share of similar businesses that changed hours on each holiday. Today it is hand-made priors in `data/peer_priors.json`, labelled as such.
