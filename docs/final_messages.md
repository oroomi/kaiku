# Final customer messages

Fonecta slide 8 asks for "your final customer messages as text". These are the messages the product sends or says today (live at https://kaiku.hankintaviikko.fi, main 1b4ac90, 7 Nov 2026). Demo business: Furry Paw Vet Clinic, the **fictional** Yext sandbox entity SinceAI07; demo date 17.12.2026 (time travel); the owner's phone and email are the team's own. English is the demo language; Finnish versions for Finnish owners are in section 9.

How this file was made: every text below was printed by the product code, not typed by hand. WhatsApp opener: `kaiku.contact.ladder.chat_text_for(suggestion, buttons=True)`. Email: `kaiku.contact.email.build_message`. Chat lines: `kaiku.chat.flow` (`proposal`, `change_prompt`, `confirm_text`, `receipt`, `discard_text`, `RECURRING_Q`) fed with the live `GET /api/feed/furry-paw` cards. Call: `kaiku.contact.call.FIRST_MESSAGE`. Cold start and no-change: `kaiku.contact.messages` via the suggest engine. The Finnish appendix in section 9 is the output of `python -m kaiku.contact.messages` (which still writes the older plain-text layout; see the note there).

## The order the owner is reached
1. Email with a one-tap decision link, no login (sent at once).
2. After `EMAIL_ESCALATE_AFTER_S` (60 s in the live config) with no decision: the WhatsApp opener below, two buttons.
3. After `WA_ESCALATE_AFTER_S` (36000 s in the live config, so the phone does not ring unprompted; code default 120): a call by Kaiku.
A decision on any channel cancels the next step.

## 1. Email (step 1)
Subject and body as built by `build_message` for the 24.12. suggestion (the link token is replaced by EXAMPLE-TOKEN):

> Furry Paw Vet Clinic: Christmas Eve hours, one question
>
> Hi, Furry Paw Vet Clinic!
>
> Last year your hours that day were 9-13.
> I suggest your hours on Christmas Eve (24.12.) are 9-13.
>
> Approve, edit or decline with one tap, no login needed:
> https://kaiku.hankintaviikko.fi/d/EXAMPLE-TOKEN
>
> Kaiku, Fonecta Connect

## 2. WhatsApp opener (step 2): a warm text in Kaiku's voice, two buttons under it
One interactive message. The body is the text; the two reply buttons are **[ Accept ]** and **[ Discard ]**. The edit is typed: "To change the hours, just reply with them." This deliberately differs from Fonecta's example buttons Approve / Edit / No thanks. Why: Accept and Discard are the two answers owners give most, so each is one tap; an Edit button only opens a second question ("which hours?"), whereas a typed reply such as "10-14" or "closed" carries the actual hours in one message. (`WA_BUTTONS=0` sends the same opener as a plain text with no buttons.)

Holiday hours (24.12.):

> Hi Furry Paw Vet Clinic! 👋 It's Kaiku, your assistant at Fonecta Connect.
>
> Christmas is around the corner, and I want to make sure none of your customers turn up at a closed door.
>
> Last year you were open 9-13 on Christmas Eve (Thursday 24.12. this year), but Connect still shows your regular hours, 9-17, for that day.
>
> Shall I set 9-13 for Christmas Eve on Google, Fonecta and everywhere else Connect publishes? Tap Accept to save it or Discard to leave it. To change the hours, just reply with them.

Buttons: `[ Accept ]` `[ Discard ]`

Closed day (25.12.):

> Hi Furry Paw Vet Clinic! 👋 It's Kaiku, your assistant at Fonecta Connect.
>
> Christmas is around the corner, and I want to make sure none of your customers turn up at a closed door.
>
> Last year you were closed on Christmas Day (Friday 25.12. this year), but Connect still shows your regular hours, 9-17, for that day.
>
> Shall I mark Christmas Day as closed everywhere Connect publishes? Tap Accept to save it or Discard to leave it. To change the hours, just reply with them.

Buttons: `[ Accept ]` `[ Discard ]`

Outside Meta's 24 hour window a free-form message cannot be sent; the ladder then sends a template first and delivers this opener with its buttons as soon as the owner replies (`tests/test_wa_chat.py::test_ladder_template_path_outside_window_then_buttons_follow_the_reply`).

## 3. The conversation after the opener (same brain on WhatsApp and on the website)
A tap on Accept (WhatsApp button or page card) saves at once, with no second question; a tap on Discard leaves the item as it is. The page chat opens empty and only speaks after the owner acts. Kaiku's lines, printed from `kaiku.chat.flow` for the live cards:

**Accept on Christmas Eve** (tests/test_chat.py::test_accept_applies_at_once_then_recurring_then_next): the receipt and, because last year's data exists, the recurring question in the same message:

> Done. 24.12. 9-13 is saved and shows on Google, Fonecta Finder and 020202 within the hour. You changed this last year as well. Do you want to make it recurring, this time of the year?

**The proposal question** (what Kaiku asks when it moves to the next item, and what a typed "yes" answers; every proposal carries its reason):

> Christmas is coming. Last year on 24.12. you were 9-13, and everywhere Connect publishes still says 9-17. Do you want to change your hours on Christmas Eve 24.12. to 9-13?

**Receipt, one per decision** (`flow.receipt`, built from the Yext write result; the model never writes it):

> Done. 24.12. 9-13 is saved and shows on Google, Fonecta Finder and 020202 within the hour.

**Recurring question**, asked only when last year's data exists (`flow.has_last_year`):

> You changed this last year as well. Do you want to make it recurring, this time of the year?

If the owner says yes: "Every Christmas Eve from now on, unless you tell me otherwise." If no: "Okay, I will ask you each time." Then Kaiku moves to the next item:

> Next: Christmas period: 6 dates. The Christmas period is coming. Last year on 24.12. you were 9-13; last year on 25.12. you were closed. Shall I set 24.12. 9-13; 25.12. closed; 26.12. closed; 31.12. 9-15; 1.1. closed; 6.1. closed?

**Suggest a change** (typed edit):

> You want to change Christmas Eve 24.12.. I suggested 9-13 because last year on 24.12. you were 9-13. What should it be?

The owner types "10-14"; Kaiku asks for confirmation:

> 10-14 on 24.12., shall I save it?

**Discard** (button, "no" or the card):

> Okay, I leave Christmas Eve 24.12. as it is.

Other cards, same shape:

> Your description on Connect reads "vacination". Shall I correct it to "vaccination"? That text shows on Google and Fonecta.
>
> (review card) The 3-star review has no reply yet, and it shows next to your listing. Shall I post this reply? "Thank you for sharing your feedback, and for your kind words about our staff. We understand that waiting 40 minutes for a booked appointment is frustrating, especially when you are caring for a pet. We appreciate you letting us know, and we are glad the team made your visit a more comfortable one."

(The review draft is written by the model from the sandbox review; the review text is sample data in Fonecta's sandbox.)

**Write failed or unfinished** (never reported as saved):

> I could not save it: the write to Yext did not go through, so nothing has changed on your listing.
>
> I have your answer, but the write to Yext has not finished, so I will not say it is saved yet.

## 4. The WhatsApp receipt after a button tap
> Done. 24.12. 9-13 is saved and shows on Google, Fonecta Finder and 020202 within the hour.

(`tests/test_wa_chat.py::test_approve_tap_applies_at_once_and_replies_with_the_receipt`.)

## 5. The call opening (step 3)
Kaiku's configured first line (ElevenLabs agent, English; `kaiku.contact.call.FIRST_MESSAGE`):

> Hi, this is Kaiku, the Fonecta Connect assistant. I'm calling about your opening hours, do you have a moment?

Finnish owner:

> Hei, täällä Kaiku, Fonecta Connectin avustaja. Soitan yrityksenne aukioloajoista, onko hetki aikaa?

The agent's system prompt limits it to the facts passed in (holiday, date, proposed hours) and. Calls were placed and answered on the team's own phone on 6 Nov (21:24Z and 21:46:53Z in `data/call_log.jsonl`; outcome in docs/call.md).

## 6. Cold start: ask instead of guess
A business with no history and no reliable source (confidence 0.50, below `ASK_BELOW` 0.6) gets a question and no proposal. English text from the engine (`ask_text_en`), sent with the buttons `[ Tell my hours ]` `[ No thanks ]`:

> Hi Furry Paw Vet Clinic! Christmas Eve is on Thursday 24.12. We do not have reliable data on your hours. Are you open on Christmas Eve 24.12.? Reply for example 9-13 or closed.

See [COLD_START.md](COLD_START.md).

## 7. No change needed (we do not invent work)
8.11. Father's Day for a vet that is closed on Sundays (`nochg` case, no buttons, no email):

> Hi Furry Paw Vet Clinic! Father's Day is on Sunday 8.11. You are normally closed on Sundays and this is not a public holiday, so no change is needed.

## 8. Decline and not understood
> Understood, no changes will be made to your hours. Thanks for replying! You can change your mind any time.
>
> No rush at all, take your time. I'll leave everything as it is until you tell me. When you're ready, just reply yes, or tell me the hours, like 9-13 or closed.

(These two are the fallback replies of the WhatsApp router when the chat brain does not take a message: `kaiku/contact/router.py`.)

## 9. Appendix: engine texts with Finnish (generated by `python -m kaiku.contact.messages`)
Finnish owners (`owner_language: fi`) get these. Note: the generator's own section 0b (the old plain-text opener) and its WhatsApp-button remarks describe an earlier layout and are left out here; the live opener is section 2 above. Finnish uses the polite plural.

### 1. Suggestion with proposed hours (the engine's suggestion text; the live opener in section 2 is built from it)

Finnish:

> Hei Furry Paw Vet Clinic! Jouluaatto on torstaina 24.12. Viime vuonna olitte auki 9-13, mutta tälle vuodelle ei ole lisätty poikkeusaukioloaikoja, joten Fonecta Connect näyttää nyt tavalliset torstain aukioloajat (9-17). Ehdotus: to 24.12. klo 9-13.
>
> Voitte hyväksyä yhdellä napautuksella, muokata aikaa tai jättää ehdotuksen väliin. Päätös on aina teidän.

English gloss:

> Hi Furry Paw Vet Clinic! Christmas Eve is on Thursday 24.12. Last year you were open 09:00-13:00 that day, but no exception hours have been added this year, so Fonecta Connect now shows your regular Thursday hours (09:00-17:00). We suggest: Thu 24.12. 09:00-13:00.
>
> Approve with one tap, edit the hours, or skip it. The decision is always yours.

### 2. Suggestion, proposal is closed

Finnish:

> Hei Furry Paw Vet Clinic! Joulupäivä on perjantaina 25.12. Viime vuonna olitte suljettuna, mutta tälle vuodelle ei ole lisätty poikkeusaukioloaikoja, joten Fonecta Connect näyttää nyt tavalliset perjantain aukioloajat (9-17). Ehdotus: pe 25.12. suljettu.
>
> Voitte hyväksyä yhdellä napautuksella, muokata aikaa tai jättää ehdotuksen väliin. Päätös on aina teidän.

English gloss:

> Hi Furry Paw Vet Clinic! Christmas Day is on Friday 25.12. Last year you were closed that day, but no exception hours have been added this year, so Fonecta Connect now shows your regular Friday hours (09:00-17:00). We suggest: Fri 25.12. closed.
>
> Approve with one tap, edit the hours, or skip it. The decision is always yours.

### 3. Ask instead of guess (low confidence or cold start)

Finnish:

> Hei Furry Paw Vet Clinic! Jouluaatto on torstaina 24.12. Meillä ei ole varmaa tietoa aukioloajoistanne. Oletteko auki jouluaattona 24.12.? Vastaa esimerkiksi 9-13 tai suljettu.

English gloss:

> Hi Furry Paw Vet Clinic! Christmas Eve is on Thursday 24.12. We do not have reliable data on your hours. Are you open on Christmas Eve 24.12.? Reply for example 9-13 or closed.

### 4. No change needed (reliability: we do not invent work)

Finnish:

> Hei Furry Paw Vet Clinic! Isänpäivä on sunnuntaina 8.11. Olette sunnuntaisin normaalisti suljettu, eikä isänpäivä ole arkipyhä, joten aukioloaikoihin ei tarvita muutosta.

English gloss:

> Hi Furry Paw Vet Clinic! Father's Day is on Sunday 8.11. You are normally closed on Sundays and this is not a public holiday, so no change is needed.

### 5. Receipt after apply (hours)

Finnish:

> Kiitos! Jouluaaton aukioloajat 9-13 on nyt tallennettu. Ne näkyvät Googlessa, Apple Mapsissa, Bingissä ja Fonectan palveluissa.

English gloss:

> Done. Christmas Eve hours 9-13 are saved and will show on Google, Fonecta Finder, 020202 and the other channels Connect publishes to.

### 5b. Receipt after apply (closed day, singular)

Finnish:

> Kiitos! Joulupäivän sulkeutuminen on nyt tallennettu. Se näkyy Googlessa, Apple Mapsissa, Bingissä ja Fonectan palveluissa.

English gloss:

> Done. Christmas Day closure is saved and will show on Google, Fonecta Finder, 020202 and the other channels Connect publishes to.

### 0. Step 1 email (subject, then body)

Finnish:

> Furry Paw Vet Clinic: Jouluaaton aukioloajat, yksi kysymys
>
> Hei, Furry Paw Vet Clinic!
>
> Viime vuonna aukioloaikanne sinä päivänä oli 9-13.
> Ehdotan, että aukioloaikanne 24.12. on 9-13.
>
> Hyväksy, muokkaa tai kieltäydy yhdellä napautuksella, kirjautumista ei tarvita:
> https://kaiku.example/d/EXAMPLE-TOKEN
>
> Kaiku, Fonecta Connect

English gloss:

> Furry Paw Vet Clinic: Christmas Eve hours, one question
>
> Hi, Furry Paw Vet Clinic!
>
> Last year your hours that day were 9-13.
> I suggest your hours on Christmas Eve (24.12.) are 9-13.
>
> Approve, edit or decline with one tap, no login needed:
> https://kaiku.example/d/EXAMPLE-TOKEN
>
> Kaiku, Fonecta Connect

### 5e. Standing-permission question after an approval

Finnish:

> Muutit tämän myös viime vuonna. Haluatko tehdä tästä toistuvan, joka vuosi tähän aikaan?

English gloss:

> You changed this last year as well. Do you want to make it recurring, this time of the year?

