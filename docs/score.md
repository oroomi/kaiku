# Listing score (`GET /api/score/{business_id}`)

How up to date and complete a business's information is everywhere Connect publishes. Shown as the hero of the owner page: big number, arc fill = score/100, caption "NEEDS UPDATES · 3 OF 7 CHECKS (example; it moves with the sandbox)". Code: `kaiku/score/engine.py` (pure `compute(listing, feed)`), route in `kaiku/score/router.py`.

Response: `{score, label_en, checks_ok, checks_total, checks: [{id, label_en, ok, points, weight, detail_en, source}], pending: [suggestion ids], today, as_of}`. `?fresh=1` bypasses the 30 s listing cache, `?quick=1` builds the feed without network signals.

| Check | Weight | Source | Full points when |
|---|---|---|---|
| hours: regular opening hours | 10 | Yext entity `hours` | all seven days have a value (open or closed) |
| holidays: holiday hours for the next holidays | 30 | Yext `holidayHours` + feed | proportional: holidays with a row (or declined by the owner) over holidays the feed detects (holiday_hours, conflict, period members) |
| agree: sources agree | 10 | feed | no pending `conflict` card |
| description | 15 | Yext `description` + feed | 10 for a description present, 5 for no pending `description` card |
| reviews: answered | 15 | feed (kind `review`), Yext reviews | no pending `review` card (zero reviews counts as ok: "No reviews yet.") |
| address: address and category | 10 | Yext `address`, `categories` | both present |
| contact: website or phone | 10 | Yext `websiteUrl`, `mainPhone` | either present |

Weights sum to 100. `pending` = every pending, non-"no change" card in the feed (the headline counts it: "3 things to fix before Christmas."). A holiday the owner declined counts as answered: the owner chose to keep regular hours.

Recompute: the page polls every 10 s and after each chat decision, card action and chain event (`?fresh=1`). Accept and chat decisions invalidate the listing cache server side. Nothing is invented: every check reads the sandbox entity or the feed.
