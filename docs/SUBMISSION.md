# Submission texts for the sinceai.app form

Copy these as written. Fill the video URL after upload.

| Field | Text |
|---|---|
| Title | Kaiku |
| One-line punchline (card text, chosen by a blind duel) | The vet is closed on Christmas Eve. Google doesn't know. Kaiku does, and asks the owner with one tap. |
| Challenge | Fonecta |
| Partner technology | FIWARE (tick) |
| Repo URL | github.com/oroomi/kaiku (private until submission) |
| Live URL | https://kaiku.hankintaviikko.fi |
| Video URL | TO BE ADDED (YouTube only; 2-3 minutes) |
| Team | VY7, solo |

## Description (100 words)
Kaiku runs Fonecta's whole chain for holiday hours. A FIWARE Orion-LD subscription detects that Christmas Eve hours are missing. Kaiku suggests last year's hours with the reason, and asks one question instead of guessing when it is unsure. The owner is reached by email, then one WhatsApp text, then a call, and answers in plain words in the chat, no login. The change is written to the team's Yext sandbox entity and read back. Kaiku learns from edits and declines and accepts standing permission. A Turku map, voice, live Aura feeds and an MCP server show the same loop at scale. Honest eval: 10 cases we wrote; 308 tests pass.

## Fonecta's required items, and where they are
| Item | Where |
|---|---|
| Working demo of all five steps | Live URL; README "demo path" |
| 2-3 minute video | URL above, after upload |
| Repo and README (run, data sources, libraries, licences) | README.md |
| 3-5 key data sources, production source, what did not work | docs/DATA_SOURCES.md |
| Final customer messages as text | docs/final_messages.md (from the real engine, with English glosses) |
| Cold-start behaviour | docs/COLD_START.md |
| Short pitch deck | docs/DECK.md (8 slides as text) |
| Bonus: a live source replacing a dataset file | Nager.Date holiday refresh; docs/DATA_SOURCES.md |

## Honest status line for the form comments
Contact is a ladder: email with the decision link (sent 6 Nov 23:48:04Z), one WhatsApp text that is the same conversation as the website chat (23:49:08Z; Meta test number, to the team's own phone, free-form text needs the 24 hour window, templates `kaiku_hours_fi` and `kaiku_hours_en` pending), then a call; the outbound English call works end to end (6 Nov 21:46:53Z: answered by the team's own phone, owner approved on the call, webhook created the decision, Yext got 24.12. 9-13, read back and verified). Evaluation is a self-consistency check on 10 hand-made cases, not Fonecta's data.
