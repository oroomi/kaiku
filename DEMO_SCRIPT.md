# Demo script (Kaiku)

Every name, date and number below is on the live page at https://kaiku.hankintaviikko.fi with the clock at 17.12.2026 (checked 7 Nov 2026 against `/api/feed/furry-paw`), except the Father's Day beat, which needs the clock at 7.11.

Opener, in the partner's words: "Connect suggests, the customer approves. This vet is closed on Christmas Eve afternoon. Connect still shows 9-17. Kaiku notices and asks the owner."
Last line: "Say yes in the chat, or answer the WhatsApp text, and the hours are in Yext. Scan this and try it." Never "vote for us".

## Before every run
1. Open `/?key=...#drawer`, press Reset: Yext holiday rows removed, clock 17.12.2026, broker entity re-seeded.
2. Laptop on `/`, phone on the live URL (the same owner page). Hotspot ready. Typed fallback for voice in a loud hall.
3. `curl https://kaiku.hankintaviikko.fi/api/status` shows broker orion-ld and today 2026-12-17.

## 2-minute version
| Time | Beat |
|---|---|
| 0:00-0:15 | Opener, then the listing score and arc on `/` and the Christmas Eve card: Connect 9-17 versus Kaiku 9-13 |
| 0:15-0:40 | Chat with Kaiku: it opens with "I noticed 2 things", the Christmas Eve bubble ("Last year you were open 9-13 ... I suggest 9-13") and the Christmas period of 6 dates, 24.12. to 6.1. (24.12. 9-13; 25.12. closed; 26.12. closed; 31.12. 9-15; 1.1. closed; 6.1. closed). Point at the cards under SUGGESTIONS FOR FURRY PAW VET CLINIC with their reasons |
| 0:40-1:05 | Contact: MESSAGE TO THE OWNER shows the thread. Email with the decision link first, then after 60 s with no decision one WhatsApp message with Accept and Discard buttons (same conversation, on the phone). Show the phone |
| 1:05-1:30 | Decide: type "yes" in the chat (or reply "yes" on WhatsApp). Kaiku says what was saved and asks "Do you want to make it recurring, this time of the year?", then the closing question "how do you want me to reach you next time? Email, WhatsApp or a call?" (the answer is stored and re-orders the ladder). Apply: written to Yext SinceAI07 and read back (`/judge?key=...`). Say: "saved to the Yext entity and confirmed; in production we update your information everywhere" |
| 1:30-1:45 | Reliability: drawer, clock to 7.11.: the card says Father's Day 8.11. "no change needed", a flag day and the clinic is closed on Sundays. If sources conflict Kaiku asks instead of guessing |
| 1:45-1:55 | The ladder's third step: after `WA_ESCALATE_AFTER_S` (600 s live) Kaiku phones the owner (approved on the call and written to Yext 6 Nov 21:46:53Z; call placed again 7 Nov 10:23:22Z). The Q&A table uses `/console?key=...` (Run the chain, Reset, who Kaiku reaches). FIWARE: curl the Store entity, one attribute, one datasetId per source |
| 1:55-2:00 | Closing line |

## 60-second version
Opener, the Christmas Eve bubble, "yes" in the chat, the Yext read-back, the Father's Day no-change note, closing line.

## Mid-demo restart line
If a judge arrives mid-demo, stop: "Let me start from the top: Connect suggests, the customer approves." Jump to the first action.

## Hard questions
1. Who is it for? The owner of a small business whose hours Fonecta Connect publishes: a vet, a cafe, a salon. The demo business is the fictional Furry Paw Vet Clinic, Fonecta's sandbox entity.
2. What was built this weekend? Everything except our MIT voice-pilot library, the `/root/hack/bin` process scripts, public APIs and data, the Yext sandbox, our VPS and tunnel. See DISCLOSURE.md: bell commit e2f7382.
3. How is it measured? Honestly: 10 hand-made cases, self-consistency only. We built a backtest with a pluggable loader and have not seen Fonecta's data. the test suite passes offline (count in README).
4. What breaks first at scale? The suggestions engine fetches the business website and Google signals per business on every build. One build for the demo clinic made 6 HTTP calls in 1.6 s warm; with real websites it grows per business and is cached only 30 s. The chat paints first without those signals.
5. Does it really reach Google? Not in the sandbox: it has no publisher listings. The Yext write is real and read back. The Yext Suggestions API returns 403 for our key, so we write the entity directly.
6. Does it really contact the owner? Yes, to the team's own contact details: an email sent 6 Nov 23:48:04Z, a WhatsApp text 23:49:08Z (free-form text needs Meta's 24 hour window; the templates are pending approval), and a call that was answered, approved and written to Yext at 21:46:53Z.
7. What if the AI is wrong? Below 0.6 confidence Kaiku asks and proposes nothing. The owner always has the last word, and the keyword parser answers if the model is down.

## Table checklist
- Laptop on power, phone on the live URL, QR card, one-page PILOT x10, 60-second screen recording on the phone as fallback.
- One person at the table at all times; battery, charger, hotspot; works on 4G.
- Never say "it normally works": switch to the recording.
