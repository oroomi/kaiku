# Demo script (Kaiku)

Opener, in the partner's words: "Connect suggests, the customer approves. This vet is closed on Christmas Eve afternoon. Google does not know. Kaiku does, and asks the owner with one tap."
The last thing said is the real number and the ask: "10 hand-made cases, 0 wrong suggestions, 2 questions asked instead of guessed. Scan this and try it on your phone." Never "vote for us".

## Before every run
1. Open the live URL, press "Reset demo": Yext holiday rows removed, clock 17.12.2026, broker entity re-seeded.
2. Laptop on `/`, phone on the live URL, QR card for `/join`. Hotspot ready. Typed fallback for voice in a loud hall.
3. `curl /api/status` shows broker orion-ld and today 2026-12-17.

## 2-minute version
| Time | Beat |
|---|---|
| 0:00-0:10 | Opener, then the headline on `/`: Google 9-17, Kaiku 9-13 |
| 0:10-0:35 | Run Jouluaatto. Point at the event strip: the broker subscription fires (Detect), the suggestion appears with its reasons (Suggest), the decision link is made (Contact, no login) |
| 0:35-1:00 | On the phone: `/d/<token>`, tap Approve. Apply: written to Yext SinceAI07 and read back. Say the sandbox wording: "saved to the Yext entity and confirmed; in production Connect passes it on to Google and the other channels" |
| 1:00-1:20 | Reliability: time travel to 2.11., run Isänpäivä 8.11.: "no change", because it is a flag day and the vet is closed on Sundays. Then a cold-start business: Kaiku asks one question |
| 1:20-1:40 | Learning: run again after an edit, the edited hours come first; standing permission |
| 1:40-1:55 | FIWARE: curl the Store entity, one attribute, five datasetIds. Then `/room` and `/map`: many owners at once |
| 1:55-2:00 | Closing line |

## 60-second version
Opener, run Jouluaatto, tap on the phone, Isänpäivä "no change", closing line.

## Mid-demo restart line
If a judge arrives mid-demo, stop: "Let me start from the top: Connect suggests, the customer approves." Jump to the first action.

## Hard questions
1. Who is it for? Connect customers who forget one-off changes: small local businesses, vets, cafes, salons.
2. What was built this weekend? Everything except our MIT voice-pilot library, public data and services. See DISCLOSURE.md: bell commit e2f7382.
3. How is it measured? Honestly: 10 hand-made cases, self-consistency only. We built a backtest with a pluggable loader and have not seen Fonecta's data.
4. What breaks first at scale? Our Orion-LD build cannot update a datasetId instance in place, so we re-create the entity. Fine for a pilot, not for thousands of businesses.
5. Does it really reach Google? Not in the sandbox: it has no publisher listings. The Yext write is real and read back.
6. Does WhatsApp really send? Yes, to the team's own phone through the Meta test number (token configured 6 Nov); free-form messages need the phone to have written first (24 hour window), the Finnish template `kaiku_hours_fi` and the English template `kaiku_hours_en` (submitted 6 Nov 21:49Z) are pending Meta approval. If a send fails the contact step gives the decision link. The call lane is proven end to end (6 Nov 21:46:53Z: Kaiku phoned the team's own phone in English, the owner said yes and "I approve", the webhook created the decision, Yext got 24.12. 9-13 and it was read back). The call escalates after `WA_ESCALATE_AFTER_S` seconds (default 120, demo config 600). Delivery statuses are logged in `data/wa_status.jsonl`. The demo reset also clears pending MCP proposals.

## Table checklist
- Laptop on power, phone on the live URL, QR card, one-page PILOT x10, 60-second screen recording on the phone as fallback.
- One person at the table at all times; battery, charger, hotspot; works on 4G.
- Never say "it normally works": switch to the recording.
