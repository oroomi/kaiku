# Submission pack: slide-8 checklist and the form text, ready to paste

Checked against the live product on 7 Nov 2026 about 11:30Z (https://kaiku.hankintaviikko.fi). Business: the **fictional** Furry Paw Vet Clinic, Fonecta's Yext sandbox entity SinceAI07 in Vantaa. Evaluation criteria (slide 7) are answered one by one in [EVAL.md](../EVAL.md). Items marked **OWNER** need Dayo's hand or decision; everything else is final text.

Character limits: the platform guide (sinceai.app, "Updated 4 Nov") states one: About at most 5,000 characters. For every other field no limit is stated in the brief; the short fields below are kept short on purpose. Check the form on Sunday and trim if it shows a counter.

## Part 1. The form, field by field (sinceai.app)

### Project name (no limit stated)
Kaiku

### Challenge (select)
Fonecta: Connect Suggests, Customer Approves

### Partner technologies (tick)
FIWARE (tick). Nothing else needs ticking for the product; ElevenLabs and Anthropic go under "Built with".

### One-line pitch / public summary line (no limit stated; 128 characters here)
Connect suggests, the customer approves: Kaiku runs the whole holiday-hours chain, by email, WhatsApp or a phone call, no login.

(Owner's pick, 7 Nov. The earlier line, kept as a spare: The vet closes early on Christmas Eve. Google does not know. Kaiku asks the owner, and the owner answers in one tap.)

### Public summary, what voters see (no limit stated; about 480 characters)
Small business owners forget to add holiday hours, so Google shows the wrong ones and customers turn up at a closed door. Kaiku notices the missing hours, suggests last year's with the exact reason, and gives the owner three ways to be reached: email first, WhatsApp if there is no decision, and a phone call if there is still none, so one unanswered channel never ends the chain. The owner taps Accept or just says "make it 10-14". We write the change to Fonecta's Yext sandbox, read it back, and tell the owner we will update their information everywhere. It learns how each owner likes to be reached. It runs live, no login.

### Description, short (no limit stated; about 300 characters)
Kaiku runs Fonecta's whole chain for holiday hours: detect the missing hours, suggest with the reason, reach the owner three ways (email, then WhatsApp, then a phone call if the earlier ones go unanswered), decide in one tap or in plain words, apply to the Yext sandbox with a read-back. A FIWARE Orion-LD broker is the spine. Live at kaiku.hankintaviikko.fi.

### Description, long: "About" (limit 5,000 characters; this text is about 4,300)
**The problem.** Fonecta Connect publishes a business's information to Google, maps, directories and AI services. Owners must log in and remember one-off changes such as holiday hours. Many forget, search results go stale, and people turn up when the business is closed.

**What Kaiku does.** Kaiku is the whole chain for holiday hours, all five steps, live. The demo business is the fictional Furry Paw Vet Clinic, Fonecta's sandbox entity SinceAI07 in Vantaa.
1. Detect. A FIWARE Orion-LD subscription fires when a holiday has no exception hours. The holiday calendar is live (Nager.Date).
2. Suggest. Kaiku proposes last year's hours (Christmas Eve 9-13, while Connect still shows 9-17) with the reason in plain words and a confidence. Below 0.6 confidence it asks one question and proposes nothing. For Father's Day, which is a flag day and not a holiday, a vet closed on Sundays gets "no change" with the reason shown, not silence.
3. Contact, no login, three ways. Every owner gets three channels, each tried only if the one before brought no decision, so an unanswered email never ends the chain. An email in plain everyday words with a decision link comes first. If nobody decides, a WhatsApp message follows with Accept and Discard buttons, and the owner can simply reply with other hours. If still nothing, Kaiku phones the owner: an ElevenLabs agent with a warm script, voice Aurora, English for the demo, dialled over a SIP trunk. A decision on any channel cancels the next step.
4. Decide. Accept, Suggest a change or Discard on the page; a button in WhatsApp; a yes on the phone; or typed hours. The customer always has the last word and nothing is written before they say yes.
5. Apply. The approved hours are written to the team's Yext sandbox entity and read back. Every receipt says "We'll update your information everywhere" and Kaiku never claims more than the read-back proves.

**It learns.** After every decision, on every channel, Kaiku asks one closing question: how would you like to be reached next time? The answer is stored as a learned preference and re-orders the ladder for that owner. An edit is proposed next time at high confidence, two declines turn a holiday into "no change", and a standing permission for recurring changes lets the next run apply without asking and tell the owner afterwards.

**Reliability.** Confidence gate, "no change" with a reason, a question instead of a guess when sources conflict, local validation of hours, and receipts built from the apply result so a failed write is never reported as saved.

**Extensibility.** The same loop already handles a description correction (a typo), a drafted reply to a review, and a holiday period of six dates as one card.

**For a Fonecta representative.** The owner page shows a listing score as a percentage, suggestion cards, a chat with voice, and what Connect publishes now. A keyed /console page lets a representative put in their own email and phone, so Kaiku reaches them, run the chain, and reset. The /eval page takes any CSV or JSON file and shows every suggestion with its reason and the hit rate. Fonecta gave no dataset format or sample during the event, so we say so plainly: our own score is a self-consistency check on 10 cases we wrote (wrong-suggestion rate 0.0, abstain rate 0.2), not accuracy on real data.

**FIWARE.** Orion-LD is the spine of the chain, not a side store. One business, five datasetIds, one truth: each source (last year, website, Google, peers, Kaiku's proposal) writes its own instance of the same attribute, and the owner's yes writes the default instance. Subscriptions fire Detect and Decide. We wrote ngsi-ld-mcp, an MCP server over any NGSI-LD broker, where an AI agent can propose but only a human can decide. Aura, our FIWARE entry, puts live Turku buses, ships and weather into the same broker as Smart Data Models entities. The /fiware page reads the live broker.

**What is real and what is sample.** The Yext writes, the emails, WhatsApp messages and phone calls are real (sent to the team's own contacts, or a visitor's own with consent). The clinic is fictional, its history, description and reviews are labelled samples we wrote, the demo date is a time-travel clock, and the sandbox has no publisher listings, so nothing is syndicated to Google. DISCLOSURE.md has the full table.

**Links.** Live: https://kaiku.hankintaviikko.fi. Repository: https://github.com/oroomi/kaiku. Video: <YouTube link>.

### Built with (technologies; no limit stated)
Python 3.12, FastAPI, Jinja2, vanilla JavaScript, SQLite, FIWARE Orion-LD (NGSI-LD) with MongoDB, Smart Data Models, MCP (ngsi-ld-mcp, our own), Fonecta Yext sandbox API, Anthropic Claude (claude-sonnet-5-5), ElevenLabs (speech to text, text to speech, phone agent), Zadarma SIP trunk, Meta WhatsApp Cloud API, SMTP (Zoho), Serper, Nager.Date, OpenStreetMap, Föli, Digitraffic AIS, Open-Meteo, MapLibre GL JS, Cloudflare Tunnel, Docker.

### What we built this weekend (no limit stated)
Everything in the repository after the first commit e2f7382 (Fri 6 Nov 18:49:59Z, a fresh repo with no code): the five-step chain, the owner page with chat and voice, the contact ladder (email, WhatsApp, phone call), the learned channel preference, standing permission, the console, the /eval page, the FIWARE spine with datasetId per source and subscriptions, the ngsi-ld-mcp server, Aura, and the documents. Brought and declared: our MIT voice-pilot library (vendored), process scripts, public data and APIs, the Yext sandbox, our server.

### Team
VY7. Dayo (Oromidayo Omisakin): product, pitch, phone, Q&A. Code written with Claude Code (Fable orchestrating, Sonnet builders and verifiers). Solo on site.

### Repository link
https://github.com/oroomi/kaiku (private until the commands in Part 3 are run; run them before pressing submit and check it logged out)

### Live demo link
https://kaiku.hankintaviikko.fi

### Demo video link
<YouTube link> (**OWNER**: public or unlisted, 2 to 3 minutes for Fonecta, plays on the vote card)

### Tech feedback (no limit stated)
Orion-LD post-v1.12.0: datasetId instances are accepted only at entity creation (POST and PATCH on attrs, upsert and batch answer 501), so we read, merge, delete and re-create the entity under a lock. A subscription query on a key inside an object value is accepted but not evaluated, and a newly added attribute does not trigger a subscription. holidayHours is not in the Smart Data Models context. Details: docs/fiware.md and docs/broker.md. Yext sandbox: the Suggestions API returns 403 for our key, the Management API accepts an inverted interval, and the sandbox has no publisher listings. WhatsApp test number: free-form and button messages deliver only inside the 24 hour window.

### GenAI tools used (no limit stated)
Claude Code (Anthropic) for all coding: Fable orchestrating, Sonnet builders and verifiers. In the product: Anthropic claude-sonnet-5-5 (chat brain, website voice loop, review reply and description drafts, Aura subscription proposals), ElevenLabs (scribe_v1 speech to text, eleven_v4 text to speech, voice Aurora, the phone agent), and Google gemini-2.0-flash as the phone agent's language model, run by ElevenLabs. The suggestion engine and its messages are rules and templates, not a model.

### GenAI in the project (no limit stated)
Coding with Claude Code, as above. In the product every model output is a draft or a spoken sentence; nothing is written to the listing before the owner says yes. The suggestion engine is not a model.

### IP terms (per member)
**OWNER**: accept for Dayo. The team owns the work; Fonecta may use it in its business (slide 8 IP note).

### Pitch deck and supporting documents (optional)
Deck: docs/KAIKU_DECK.pdf (8 slides, 6 MB, built 7 Nov 17:40Z from docs/DECK.md with frames of the film and live screenshots; upload it in this field). Text version: docs/DECK.md. Supporting: README.md, EVAL.md, DISCLOSURE.md, docs/DATA_SOURCES.md, docs/final_messages.md, docs/COLD_START.md. No ZIPs.

### FIWARE Open Innovation Award paragraph (criteria: integration 35 / technical 30 / innovation 20 / practical 15; no limit stated, about 1,900 characters)
Kaiku uses FIWARE as the spine of a real product, not as a side store. Integration (35): the Orion-LD NGSI-LD broker holds the business as a Smart Data Models Store entity, and each step of Fonecta's chain happens in it. Detect is a subscription firing, Suggest is a proposed instance, Decide is the owner's tap writing the default instance, and the broker notification applies the change to the listing. The Yext write never depends on the broker, and the page says "broker offline" if it is down. Technical (30): the attribute holidayHours has one instance per source, told apart by datasetId (last year, website, Google, peers, Kaiku's proposal), each with observedAt, so the disagreement between sources is visible in one GET and nothing is merged lossily. We also report what did not work on Orion-LD post-v1.12.0: datasetId instances are accepted only at entity creation, subscription queries do not match keys inside object values, and a new attribute does not fire a subscription. We built around each. Innovation (20): we wrote ngsi-ld-mcp, an MCP server for any NGSI-LD broker, mounted read-only for the public: an AI agent can read, propose and subscribe, but only a human can decide, and the broker holds both instances so it is the audit log. Aura, our entry film and the /aura page, puts live Turku buses (Föli), ships (Digitraffic AIS) and weather (Open-Meteo) into the same broker as Smart Data Models Vehicle and WeatherObserved entities, and an agent proposes a geo subscription that a person approves. Practical (15): a small business owner gets a plain message instead of a login, and the same pattern (many sources, one truth, human approval) fits any data a platform publishes. Everything is live and read-only at https://kaiku.hankintaviikko.fi/fiware, with the repository link, docs/fiware.md and a 60 second verify list of curl commands.

### FIWARE award fields (the Field Guide form asks these four when FIWARE is ticked; paste as is)
- **Technologies used (from the list):** NGSI-LD; Context Broker (Orion-LD); Smart Data Models (Store from PointOfInterest; Vehicle and WeatherObserved in Aura).
- **How they fit the architecture (min 40 characters):** Orion-LD is the spine of Fonecta's chain, not a side store. The business is a Smart Data Models Store entity (urn:ngsi-ld:Store:furry-paw). Its attribute holidayHours carries one instance per source, told apart by datasetId (lastyear, website, google, peers) plus Kaiku's proposal, each with observedAt. A subscription on holidayHoursStatus fires Detect; the owner's tap writes the default instance (Decide); the broker's notification applies the change to the Yext listing (Apply). Our ngsi-ld-mcp server lets an AI agent read, propose and subscribe on any NGSI-LD broker while only a human can decide; the broker holds both instances, so it is also the audit log.
- **Evidence link (https, public, no confidential data):** https://github.com/oroomi/kaiku (public from submission time), live broker view https://kaiku.hankintaviikko.fi/fiware, judge check `curl https://kaiku.hankintaviikko.fi/api/fiware/entity` (five holidayHours instances on 7 Nov 17:06Z: default + lastyear, website, google, peers), recording `<YouTube link>`.
- **Live demo:** yes, in the Sunday final (the 3:25 to 3:50 beat of the stage script opens /fiware on the projector).

## Part 2. Slide-8 checklist, item by item

| # | Fonecta asks for | Our answer | Where | State |
|---|---|---|---|---|
| 1 | Working demo of the five steps | Live now. Open the URL with the demo clock at 17.12.2026 (the live default), press Accept on Christmas Eve: Detect, Suggest, Contact, Decide, Apply with a Yext read-back. A Fonecta representative can try it on their own phone through `/console` | https://kaiku.hankintaviikko.fi, [README](../README.md) "Demo path" | done |
| 2 | 2-3 minute video | YouTube upload | `<YouTube link>` | **OWNER**: upload and paste the link into README, this file and the form |
| 3 | Code repository with a README: how to run it, data sources, libraries and licences | README has the 3-command run, the data-source pointers and the licence table covering every entry of `requirements.txt` | [README](../README.md), [DISCLOSURE](../DISCLOSURE.md) | done once the repo is public (Part 3) |
| 4 | 3-5 key data sources, where Connect would get them in production, what did not work | Five sources with a production column and a failures list | [DATA_SOURCES.md](DATA_SOURCES.md) | done |
| 5 | Final customer messages as text | Email, WhatsApp message with Accept / Discard, chat lines, receipts, recurring question, closing channel question, discard line, call script, cold-start question; Finnish appendix | [final_messages.md](final_messages.md) | done |
| 6 | How it behaves for a customer with no history | Asks one question and proposes nothing below 0.6 confidence | [COLD_START.md](COLD_START.md) | done |
| 7 | Short pitch deck | 8 slides as text with every number sourced | [DECK.md](DECK.md) | done as text; PDF is **OWNER** if wanted |
| BONUS | Replace a dataset file with a live source, say what we learned | Four live sources with receipts: Nager.Date, the Yext sandbox read, OpenStreetMap, Föli/Digitraffic/Open-Meteo through the broker | [DATA_SOURCES.md](DATA_SOURCES.md) "Bonus" | done |

## Run it in 3 commands
```bash
git clone https://github.com/oroomi/kaiku && cd kaiku
python3 -m venv .venv && .venv/bin/pip install -r requirements.txt
.venv/bin/uvicorn kaiku.app:app --host 127.0.0.1 --port 8210   # http://127.0.0.1:8210
```
Without keys the chain still runs and each lane says what is missing; a local instance never sends email, WhatsApp or calls (`PUBLIC_URL` is not the production URL). Tests: `.venv/bin/python -m pytest -q` gives 454 passed, 7 skipped on the box with its `.env` (7 Nov 2026); in a fresh checkout `tests/test_email.py::test_real_smtp_path` also fails because it needs the box's SMTP settings.

## Facts a judge can check in one command each
| Claim | Command | Value on 7 Nov 11:20Z |
|---|---|---|
| Listing score | `curl https://kaiku.hankintaviikko.fi/api/score/furry-paw` | 40, "Needs updates", 3 of 7 checks, 4 pending cards (it moves with the sandbox state) |
| Suggestion with reason | `curl https://kaiku.hankintaviikko.fi/api/feed/furry-paw` | Christmas Eve 9-13, confidence 0.75, reasons from last year and from what Connect shows |
| What Yext holds | `curl https://kaiku.hankintaviikko.fi/api/listing/furry-paw` | entity SinceAI07, description marked as sample text, no holiday rows before an approval |
| Chat opens empty | `curl https://kaiku.hankintaviikko.fi/api/chat/open` | `"messages": []` |
| Status | `curl https://kaiku.hankintaviikko.fi/api/status` | broker orion-ld, WhatsApp configured, Yext entity SinceAI07, today 2026-12-17 |
| FIWARE subscriptions | `curl https://kaiku.hankintaviikko.fi/api/fiware/subscriptions` | two active, `kaiku-holiday-hours-missing` and `kaiku-holiday-hours-resolved` |
| Eval sample | `curl https://kaiku.hankintaviikko.fi/api/eval/sample` | our 10 cases, each with its reason |

## Product facts for the form comments
- Contact is a ladder: email (plain words, decision link) at once, a WhatsApp message with Accept and Discard after 60 s without a decision (`EMAIL_ESCALATE_AFTER_S`), then a call by Kaiku after 600 s (`WA_ESCALATE_AFTER_S`). A decision on any channel cancels the next step. The closing question on every channel, how the owner would like to be reached next time, is stored and re-orders the ladder.
- Call lane: an ElevenLabs agent (voice Aurora, eleven_v4, language model gemini-2.0-flash) over a Zadarma SIP trunk, English for the demo, Finnish per owner. The owner approved on a call and Yext was written and read back on 6 Nov at 21:46:53Z; calls were placed again on 7 Nov at 10:18Z and 10:23Z.
- We deliberately differ from Fonecta's example buttons Approve / Edit / No thanks: Accept and Discard are the two common answers and each is one tap; an edit is typed, because the typed hours carry the actual answer in one message.
- WhatsApp: Meta test number, messages only to numbers registered in the test app; free-form text delivers only inside Meta's 24 hour window; the templates `kaiku_hours_fi` and `kaiku_hours_en` were pending at last check (6 Nov).
- Evaluation is a self-consistency check on 10 hand-made cases, not Fonecta data, because Fonecta gave no dataset format or sample during the event.

## Part 3. At submission time (do NOT run before the owner says go)

Run from a clean clone of the final branch, after the film is uploaded and the `<YouTube link>` is pasted into README.md and this file.

### 3a. Files that must not ship
| Path | Why |
|---|---|
| `kaiku/web/static/mock_v3.html`, `kaiku/web/static/mock_v3b.html` | the two static mock pages with sample data; the product page replaces them and CLAUDE.md forbids shipping mock html |
| `video/` (33 tracked files: Remotion sources, `video/NOTES.md`, `video/trailer/products/proofroom.json` and `radar.json`, which belong to other products) | film production, not the product; contains other projects' trailer files; music and template licences are not documented in the repo |
| `scripts/approval_*`, `scripts/capture_*`, `scripts/score_approval.py`, `scripts/score_v3.py`, `scripts/v2_*`, `scripts/v3_*` (16 files) | film tooling with `/root/hack` paths, nothing in the product or the tests uses them |
| `docs/img/kaiku_poster.png` | video poster, not referenced by any document |
| `agent_payload.json`, `VOICE_SPIKE.md` | the first Finnish call spike; stale next to `docs/call.md` and holds a personal phone number |
| `TASKS.md`, `.mcp.json` | internal task board and local tool config |
| `data/yext_snapshot_20261106T234652157574Z.json` | a runtime snapshot that was committed although its pattern is gitignored |
| `CLAUDE.md`, `DESIGN.md` | internal builder instructions with private paths (`/root/hack/dossiers`) and the pre-event Approve / Edit / No thanks wording. Optional: they show how we work; keep them only if the owner wants that visible, then replace the private paths first |

Check after removal that `.venv`, `.env`, `data/*.jsonl` runtime logs, `data/demo_contact.json` and any `video/*.mp4` are not tracked (`tests/test_repo_hygiene.py` checks the first group).

### 3b. Git history warning (decision for the owner)
- A team member's personal phone number is in the history (`docs/call.md`, `VOICE_SPIKE.md`, `tests/test_call.py` in older commits). The current tree has it scrubbed from `docs/call.md` and `tests/test_call.py`; `VOICE_SPIKE.md` is on the removal list. Making the repo public publishes the history. Either accept it (it is the team's own demo number), or rewrite: `git filter-repo --replace-text <(echo '+<the number>==>+358401234567')`, which changes every commit hash, so the DISCLOSURE.md and README references to the bell commit e2f7382 must then be updated to the new hash.
- **Branch `task/video-v4` in the main checkout must not be pushed or merged as is**: it tracks about 2,100 files including a 195 MB `.pack` file under `video/`. Merge only this branch (`task/submission`) and film files by hand.

### 3c. Commands
```bash
cd /root/hack/kaiku                      # main checkout; be on main with a clean tree
git merge --no-ff task/submission
git rm -r kaiku/web/static/mock_v3.html kaiku/web/static/mock_v3b.html video scripts \
       docs/img/kaiku_poster.png agent_payload.json VOICE_SPIKE.md TASKS.md .mcp.json \
       data/yext_snapshot_20261106T234652157574Z.json
# optional, see table: git rm CLAUDE.md DESIGN.md
.venv/bin/python -m pytest -q tests/test_repo_hygiene.py        # 3 passed
.venv/bin/python -m pytest -q                                   # 454 passed, 1 failed (smtp) on the box
git commit -m "Prepare public release: remove mock pages and film tooling

Co-Authored-By: Claude Fable 5.1 <noreply@anthropic.com>"
git grep -nE "sk-[A-Za-z0-9]{10}|xi-api-key: [A-Za-z0-9]|Bearer [A-Za-z0-9]{10}|<the number>"   # expect only code that reads keys from the environment
git push origin main
gh repo edit oroomi/kaiku --visibility public --accept-visibility-change-consequences
curl -s -o /dev/null -w "%{http_code}\n" https://github.com/oroomi/kaiku          # 200 logged out
git clone https://github.com/oroomi/kaiku /tmp/kaiku_check && cd /tmp/kaiku_check \
  && python3 -m venv .venv && .venv/bin/pip install -r requirements.txt \
  && .venv/bin/uvicorn kaiku.app:app --port 8299 &                                # the 3 commands work
```
Then redeploy the live site from the same commit with `/root/hack/bin/deploy.sh` so the live page and the repo match, and confirm `https://kaiku.hankintaviikko.fi/static/mock_v3.html` returns 404.

### 3d. Last-hour sweep (Sunday 09:00 to 09:45 EET)
- README first screen: what and for whom, live URL, 3-command run, architecture diagram; headings Architecture, Evaluation, Disclosure.
- `<YouTube link>` replaced everywhere (README, this file, the form); the video plays logged out.
- Form: project name, pitch, summary, About (at most 5,000 characters), repo, live link, FIWARE ticked, IP terms for every member, video; submit before 10:00 EET and check the platform shows it received.
