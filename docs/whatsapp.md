
## Language
English is the default (`owner_language: en`): buttons **Approve / Edit / No thanks** with the same ids `approve:<id>`, `edit:<id>`, `decline:<id>`, English suggestion, ask, no-change, edit-prompt ("Reply with the new hours, like 9-13, or 'closed'."), receipt, decline thanks and unknown-reply texts. Finnish stays per owner (`owner_language: fi`; `WhatsAppClient`/`whatsapp.FI_BUTTONS`). Replies to an owner use the language remembered when the suggestion was sent. Inbound free text accepts both languages (yes/approve/ok/sure, no/no thanks/decline, `9-13`, `9am-1pm`, `nine to one`, `closed`, plus the Finnish words).

## Template path and the 24 hour window

Meta only lets us send free-form messages (text and the interactive Approve / Edit / No thanks buttons) to someone who wrote to us in the last 24 hours. Outside that window the only thing that gets through is an approved template message. The owner of a business will usually be outside the window when Kaiku has a suggestion, so the first message has to be a template.

The Finnish template is `kaiku_hours_fi` (language fi, category UTILITY); an English owner uses a template only when `WA_TEMPLATE_NAME_EN` names an approved English one (same parameters, language en), otherwise the English interactive buttons are sent. Its body has four text parameters: business name, date like 24.12., hours like 9-13, and the reason. It carries three quick-reply buttons, Hyväksy, Muokkaa and Ei kiitos. `WhatsAppClient.send_template_hours(to, business_name, date_fi, hours_fi, reason_fi, suggestion_id)` builds and sends it. The button payloads are the same ids as the interactive message (`approve:<id>`, `edit:<id>`, `decline:<id>`), so the inbound webhook handles the tap as `type: "button"` with `button.payload` and nothing else changes.

It is off by default. Set `WA_TEMPLATE_NAME=kaiku_hours_fi` in the environment of the app and the ladder sends the template instead of the interactive message for hours suggestions (ask and no-change messages are unchanged). Leave it unset and the ladder behaves as before. Switch it on only after Meta has approved the template. Once the owner taps a button the window opens and normal messages work for 24 hours.

Live tests: anything that sends a real message is skipped unless `KAIKU_LIVE=1` is set.
