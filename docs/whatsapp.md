## WhatsApp is the website chat, in words (owner decision 7 Nov)

No buttons by default. The ladder's WhatsApp step sends ONE plain text built from the chat opening for the business (`kaiku.chat.router.opening`: the intro line, then one line per suggestion and note, exactly what the website chat shows on load) and ends with the line "Reply in your own words." Example at the demo date 17.12. (full text in `docs/final_messages.md`, item 0b):

> Hi Furry Paw Vet Clinic. I noticed 2 things.
>
> Christmas Eve 24.12.: 09:00-13:00. ... We suggest: Thu 24.12. 09:00-13:00.
>
> Christmas period: 6 dates. ...
>
> Reply in your own words.

- `WA_BUTTONS=1` brings the interactive Approve / Edit / No thanks message back (code unchanged, same ids). Unset or anything else = the text above.
- Finnish owners get the Finnish suggestion text plus "Vastaa omin sanoin." (the chat opening is English). Businesses the chat does not know get the plain suggestion text plus the reply line. Kind `no_change` stays a plain reassurance without the reply line.
- Outside the 24 h window nothing changes: the approved template (or `hello_world`) goes first; when the owner answers it, the stored opening text (not buttons) is delivered. `WA_TEMPLATE_NAME` / `WA_TEMPLATE_NAME_EN` behave as before.
- Inbound: any text from the owner's phone (`OWNER_WHATSAPP`) goes to the chat brain (`kaiku.chat.brain.respond`) with session id `wa:<digits of the phone>` and the owner's business (`furry-paw`; the business remembered for the suggestion wins). The session is the chat package's own in-memory store (`kaiku.chat.router.session`), so a second message from the same phone continues it. The reply goes back with `send_text`; the session carries `via: whatsapp`.
- Decisions made in that conversation (approve, edit with new times, decline, the standing-permission yes) call the same functions as the web chat, `kaiku.chat.actions.decide` / `set_standing_permission`: `chain.on_decision` when a chain run is waiting, else `chain.post_decision`. Decision events carry `via: whatsapp`.
- Button payloads (`approve:<id>`, `edit:<id>`, `decline:<id>`, template quick replies) still work and now run through the same `actions.decide` path. The Edit button sends the edit prompt and the next text is read as the new hours.
- Fallback: without `ANTHROPIC_API_KEY` (or when the model call fails) the brain's own keyword parser answers (yes / no / 9-13 / closed / "9 to 1"). If the brain itself raises, the original keyword parser in `router.parse_free_text` takes over and a reply the parser does not understand gets the short "did not understand" text, so the lane never goes silent.
- Texts from any other phone number are ignored. The receipt after apply ("Done. ... saved and will show on ...") and the 24 h window logic and `data/wa_status.jsonl` are unchanged. The receipt comes from apply; the brain's own reply to an approval adds the one standing-permission question ("Last year 9-13, this year 9-13 again. Want me to do this every Christmas Eve?").

Also fixed on the way: `kaiku.chat.util.hours_text` crashed on a `period` feed item (the Christmas period), which broke the chat opening from 17.12.; it now prints "24.12. 9-13; 25.12. closed".


## Language
English is the default (`owner_language: en`): buttons **Approve / Edit / No thanks** with the same ids `approve:<id>`, `edit:<id>`, `decline:<id>`, English suggestion, ask, no-change, edit-prompt ("Reply with the new hours, like 9-13, or 'closed'."), receipt, decline thanks and unknown-reply texts. Finnish stays per owner (`owner_language: fi`; `WhatsAppClient`/`whatsapp.FI_BUTTONS`). Replies to an owner use the language remembered when the suggestion was sent. Inbound free text accepts both languages (yes/approve/ok/sure, no/no thanks/decline, `9-13`, `9am-1pm`, `nine to one`, `closed`, plus the Finnish words).

## Template path and the 24 hour window

Meta only lets us send free-form messages (text and the interactive Approve / Edit / No thanks buttons) to someone who wrote to us in the last 24 hours. Outside that window the only thing that gets through is an approved template message. The owner of a business will usually be outside the window when Kaiku has a suggestion, so the first message has to be a template.

The Finnish template is `kaiku_hours_fi` (language fi, category UTILITY); an English owner uses a template only when `WA_TEMPLATE_NAME_EN` names an approved English one (`kaiku_hours_en`, quick replies Approve / Edit / No thanks, submitted to Meta 6 Nov 21:49Z, pending) (same parameters, language en), otherwise the English interactive buttons are sent. Its body has four text parameters: business name, date like 24.12., hours like 9-13, and the reason. It carries three quick-reply buttons, Hyväksy, Muokkaa and Ei kiitos. `WhatsAppClient.send_template_hours(to, business_name, date_fi, hours_fi, reason_fi, suggestion_id)` builds and sends it. The button payloads are the same ids as the interactive message (`approve:<id>`, `edit:<id>`, `decline:<id>`), so the inbound webhook handles the tap as `type: "button"` with `button.payload` and nothing else changes.

It is off by default. Set `WA_TEMPLATE_NAME=kaiku_hours_fi` in the environment of the app and the ladder sends the template instead of the interactive message for hours suggestions (ask and no-change messages are unchanged). Leave it unset and the ladder behaves as before. Switch it on only after Meta has approved the template. Once the owner taps a button the window opens and normal messages work for 24 hours.

Live tests: anything that sends a real message is skipped unless `KAIKU_LIVE=1` is set.
