# Submission pack: Fonecta slide 8, item by item

Checked against the live product on 7 Nov 2026 01:50Z (https://kaiku.hankintaviikko.fi, main 1b4ac90). Business: the **fictional** Furry Paw Vet Clinic, Fonecta's Yext sandbox entity SinceAI07 in Vantaa. The sandbox description and the two reviews are sample text written by team VY7 and labelled so. Evaluation criteria (slide 7) are answered one by one in [EVAL.md](../EVAL.md).

## Fields for the sinceai.app form
| Field | Text |
|---|---|
| Title | Kaiku |
| One-line punchline | The vet is closed on Christmas Eve. Google doesn't know. Kaiku does, and asks the owner with one tap. |
| Challenge | Fonecta |
| Partner technology | FIWARE (tick) |
| Repo URL | github.com/oroomi/kaiku (private until submission; returns 404 to the public today) |
| Live URL | https://kaiku.hankintaviikko.fi |
| Video URL | not uploaded yet, see item 2 |
| Team | VY7, solo |

Description (100 words): Kaiku runs Fonecta's whole chain for holiday hours. A FIWARE Orion-LD subscription detects that Christmas Eve hours are missing. Kaiku suggests last year's hours with the reason, and asks one question instead of guessing when it is unsure. The owner is reached by email, then a WhatsApp message with Accept and Discard buttons, then a call, and answers in plain words or one tap, no login. The change is written to the team's Yext sandbox entity and read back. Kaiku learns from edits and declines and stores standing permission. Honest eval: 10 cases we wrote, not Fonecta's data; 362 tests pass.

## Slide 8, item by item
| # | Fonecta asks for | Our answer | Where |
|---|---|---|---|
| 1 | Working demo of the five steps | Live now. Open the URL, set the clock to 17.12.2026 (already the live default), accept Christmas Eve: Detect, Suggest, Contact, Decide, Apply with a Yext read-back. Run it yourself in 3 commands (below). | https://kaiku.hankintaviikko.fi; [README](../README.md) "Demo path" |
| 2 | 2-3 minute video | Approval cut: `video/kaiku_approval_cut.mp4` (2:10, made on sample pages, per `video/NOTES.md`). The final cut recorded on the live page follows. The file is not in git and I could not find it on the build box on 7 Nov 02:00Z, so the YouTube upload is still open. | `video/NOTES.md`; YouTube URL to be added |
| 3 | Code repository with a README: how to run it, data sources, libraries and licences | Repository github.com/oroomi/kaiku (private until submission). README has the 3-command run, the data-source table and the licence list (every entry of `requirements.txt` is covered). | [README](../README.md), [DISCLOSURE](../DISCLOSURE.md) |
| 4 | 3-5 key data sources, where Connect would get them in production, what did not work | Five sources in a table with a production column, plus the failures list. | [DATA_SOURCES.md](DATA_SOURCES.md) |
| 5 | Final customer messages as text | The email, the WhatsApp opener with Accept / Discard, the chat lines, the receipt, the recurring question, the discard line, the call opening, the cold-start question, all printed from the product code; Finnish appendix. | [final_messages.md](final_messages.md) |
| 6 | How it behaves for a customer with no history | Asks one question in English, proposes nothing below 0.6 confidence. | [COLD_START.md](COLD_START.md) |
| 7 | Short pitch deck | 8 slides as text with every number sourced. | [DECK.md](DECK.md) |
| BONUS | Replace a dataset file with a live source, tell what you learned | Four live sources with receipts: Nager.Date over the holiday file, the Yext sandbox read for the listing and score, OpenStreetMap (813 Turku businesses), Föli/Digitraffic/Open-Meteo through the broker. Learned: every live source needs a timeout and a fallback; the sandbox has no history, so "last year" is still a labelled sample. | [DATA_SOURCES.md](DATA_SOURCES.md) "Bonus" |

## Run it in 3 commands
```bash
git clone https://github.com/oroomi/kaiku && cd kaiku
python3 -m venv .venv && .venv/bin/pip install -r requirements.txt
.venv/bin/uvicorn kaiku.app:app --host 127.0.0.1 --port 8210   # http://127.0.0.1:8210
```
Without keys the chain still runs and each lane says what is missing; a local instance never sends email, WhatsApp or calls (`PUBLIC_URL` is not the production URL). Tests: `.venv/bin/python -m pytest -q`: 362 passed, 6 skipped on main with the box's `.env`; in a fresh checkout without SMTP settings `tests/test_email.py::test_real_smtp_path` fails (361 passed, 1 failed).

## Facts a judge can check in one command each
| Claim | Command | Value on 7 Nov 01:50Z |
|---|---|---|
| Listing score | `curl https://kaiku.hankintaviikko.fi/api/score/furry-paw` | 45, "Needs updates", 3 of 7 checks, 3 pending cards |
| Suggestion with reason | `curl https://kaiku.hankintaviikko.fi/api/feed/furry-paw` | Christmas Eve 9-13, confidence 0.75, reasons from last year and from what Connect shows |
| What Yext holds | `curl https://kaiku.hankintaviikko.fi/api/listing/furry-paw` | entity SinceAI07, holiday row 24.12. 9-13, description marked as sample text |
| Chat opens empty | `curl https://kaiku.hankintaviikko.fi/api/chat/open` | `"messages": []` |
| Status | `curl https://kaiku.hankintaviikko.fi/api/status` | broker orion-ld, WhatsApp configured, Yext entity SinceAI07 |

## Product facts for the form comments
- Contact is a ladder: email with the decision link first (sent 6 Nov 23:48:04Z, `data/email_log.jsonl`), then after 60 s without a decision a WhatsApp opener (a warm text in Kaiku's voice with two buttons, Accept and Discard, under it and the line "To change the hours, just reply with them."; text sent 6 Nov 23:49:08Z, `data/wa_sends.jsonl`), then a call by Kaiku after `WA_ESCALATE_AFTER_S` (36000 s in the live config so the phone does not ring unprompted). A decision on any channel cancels the next step.
- We deliberately differ from Fonecta's example buttons Approve / Edit / No thanks: Accept and Discard are the two common answers and each is one tap; an edit is typed, because the typed hours carry the actual answer in one message instead of a second question.
- The page: listing score (7 checks), cards with Accept / Suggest a change / Discard; Accept applies at once; the chat opens empty and Kaiku confirms, asks the recurring question only when last year's data exists, then moves to the next item; every proposal carries its reason; one receipt per decision; chat memory persists; learned preferences change the next suggestion; standing permission is stored.
- Meta test number, messages only to the team's own phone; free-form text delivers only inside Meta's 24 hour window; the templates `kaiku_hours_fi` and `kaiku_hours_en` were pending at last check. The English outbound call worked end to end on 6 Nov (answered by the team's own phone, owner approved, Yext write read back; [call.md](call.md)).
- Evaluation is a self-consistency check on 10 hand-made cases, not Fonecta's hidden data.
