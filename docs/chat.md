# Owner chat (v4): Kaiku proposes, the owner decides

Code: `kaiku/chat/flow.py` (texts and the stage machine), `brain.py` (model + fallback), `router.py` (routes), `actions.py` (decide).
The page's chat opens empty; `chat.router.opening` still builds the old opening for WhatsApp (`contact/ladder.chat_text_for`) and `/api/chat/open?full=1`.

## Session state (`router.session`)
`focus` (card id), `stage` (None | proposed | ask_new | confirm), `pending` (the owner's own value waiting for a yes), `followup` (the recurring question waits).
Only an explicit focus counts (Accept, Suggest a change, a hand-off, the WhatsApp opening). A bare "yes" with no proposal decides nothing: "I have not proposed anything yet. Accept a suggestion above and I will talk you through it."

## Flow
1. **Accept** -> proposal (nothing written), stage `proposed`.
   - holiday_hours: "<Season> is coming. Do you want to change your hours on <holiday name> <date> to <hours>? Everywhere Connect publishes still says <regular hours that day>." Season = "Christmas" for 24.12. to 6.1., else the holiday name ("Midsummer Eve is coming"). Closed proposal: "Do you want to mark <name> <date> as closed?". No proposed hours: "I have no ready hours for ... What should they be?" (stage ask_new).
   - period: "The <period name> is coming: <date list>. Shall I set all of them?" (only the dates not yet decided).
   - description: `Shall I correct "vacination" to "vaccination" in your description?`; missing: "Your listing has no description. Shall I publish this one? <draft>".
   - review: `Shall I post this reply to the <n>-star review? "<draft>"`.
2. **yes** -> `actions.decide(approve, via web|whatsapp|voice)`: holiday write + read-back; period = every undecided member date (ids equal the single-date card ids, so a date already decided is skipped); description write; review post or stored reply.
3. **Receipt** (built from the apply result, `flow.receipt`): "Done. 24.12. 9-13 is saved and shows on Google, Fonecta Finder and 020202 within the hour." Period: "Done. All 5 dates are saved and show on ...". Description: "Done. Your description is saved and shows on ...". Review posted: "Done. Your reply is posted on the review."; stored only: "Your reply is stored. The sandbox key cannot post review comments, so it is not on the review yet."; write failed: "I could not save it: the write to Yext did not go through, so nothing has changed on your listing."; write not finished: "I have your answer, but the write to Yext has not finished, so I will not say it is saved yet." The model never writes this text: after any decide call the reply is replaced by the receipt.
4. **Recurring question**, ONLY when there is last-year data (`flow.has_last_year`: the suggestion's `last_year` or an exception the business set on the same day last year): "You changed this last year as well. Do you want to make it recurring, this time of the year?" yes -> standing permission (learn prefs) and "Every <holiday name> from now on, unless you tell me otherwise."; no -> "Okay, I will ask you each time." While it waits, a yes/no answers it and never the next card; any other message lets the question lapse.
5. **Next card**: "Next: <next card title>. <its proposal question>" (focus moves, stage proposed). None left: nothing is added.
6. **no** at any stage -> decline (learn event) -> "Okay, I leave it as it is." **Discard** on a card -> "Okay, I leave <title> as it is." / "...your description as it is." / "...the review without a reply." / "...the <period> as it is."

## Suggest a change
"You want to change <title>. I suggested <hours> because <first reason in plain words>. What should it be?" (stage ask_new). Hours (10-14, 9 to 1, closed) -> "<value> on 24.12., shall I save it?" (period: "<value> on all of these dates, shall I save it?") -> yes -> decide(edit) -> receipt. Description: "...What should the description say?" and the owner's own text replaces it ("Shall I save this as your description? "<text>""); review: "...What should the reply say?" -> "Shall I post this as your reply? "<text>"".

## Who handles what
yes / no / hours / the owner's own text inside a stage are handled deterministically (`flow.handle`, no model call, so they are fast and cannot overclaim). Everything else goes to claude-sonnet-5-5 with the focus and stage in its system prompt (tools: decide, set_standing_permission, get_feed); without a key, or if the API fails, `brain.fallback_reply` does yes / no / hours / text. WhatsApp uses the same `brain.respond`; its session has a focus from the opening and no stage, so a "yes" applies that card directly.

## Known limits
Period edits apply one set of hours to all undecided dates. Finnish owners skip the stage handler (English texts only for the demo). `tests/test_email.py::test_real_smtp_path` fails on main as well (environment SMTP).
