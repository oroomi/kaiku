# Final customer messages

Demo business: Furry Paw Vet Clinic (fictional Yext sandbox entity). Items 1 to 4 are the exact Suggestion texts from `python3 -m kaiku.suggest.cli --business data/furry_paw.json` (no network): 24.12. hours, 25.12. closed, 24.12. with no history (ask), 8.11. no change. Text as sent over WhatsApp, with English glosses.

## 0b. Step 2 WhatsApp opening: ONE plain text, the same intro and suggestion lines the website chat shows on load (demo date 17.12., fictional Furry Paw Vet Clinic), no buttons

Finnish:

> (Finnish owners get the Finnish suggestion text followed by "Vastaa omin sanoin."; the website chat opening is English only.)
>
> Hei, Furry Paw Vet Clinic!
>
> Jouluaatto on torstaina 24.12.
> Viime vuonna aukioloaikanne tuona päivänä oli 9-13.
> Googlessa näkyy nyt 9-17, mikä ei vastaa ehdotustamme, joten asiakas voi saapua suljetun oven eteen.
>
> Ehdotamme, että jouluaattona (24.12.) aukioloaikanne on 9-13.
> Voitte hyväksyä yhdellä napautuksella, muokata aikaa tai jättää ehdotuksen väliin. Päätös on aina teidän.
>
> Vastaa omin sanoin.

English gloss:

> Hi Furry Paw Vet Clinic. I noticed 2 things.
>
> Christmas Eve 24.12.: 09:00-13:00. Hi Furry Paw Vet Clinic! Christmas Eve is on Thursday 24.12. Last year you were open 09:00-13:00 that day, but no exception hours have been added this year, so Fonecta Connect now shows your regular Thursday hours (09:00-17:00). We suggest: Thu 24.12. 09:00-13:00.
>
> Christmas period: 6 dates. 24.12. 09:00-13:00; 25.12. closed; 26.12. closed; 31.12. 09:00-15:00; 1.1. closed; 6.1. closed. Want me to handle this period every year?. I suggest 24.12. 9-13; 25.12. closed; 26.12. closed; 31.12. 9-15; 1.1. closed; 6.1. closed.
>
> Reply in your own words.

## 1. Suggestion with proposed hours (the plain suggestion text; WhatsApp buttons Approve / Edit / No thanks only with WA_BUTTONS=1)

Finnish:

> Hei Furry Paw Vet Clinic! Jouluaatto on torstaina 24.12. Viime vuonna olitte auki 9-13, mutta tälle vuodelle ei ole lisätty poikkeusaukioloaikoja, joten Fonecta Connect näyttää nyt tavalliset torstain aukioloajat (9-17). Ehdotus: to 24.12. klo 9-13.
>
> Voitte hyväksyä yhdellä napautuksella, muokata aikaa tai jättää ehdotuksen väliin. Päätös on aina teidän.

English gloss:

> Hi Furry Paw Vet Clinic! Christmas Eve is on Thursday 24.12. Last year you were open 09:00-13:00 that day, but no exception hours have been added this year, so Fonecta Connect now shows your regular Thursday hours (09:00-17:00). We suggest: Thu 24.12. 09:00-13:00.
>
> Approve with one tap, edit the hours, or skip it. The decision is always yours.

## 2. Suggestion, proposal is closed

Finnish:

> Hei Furry Paw Vet Clinic! Joulupäivä on perjantaina 25.12. Viime vuonna olitte suljettuna, mutta tälle vuodelle ei ole lisätty poikkeusaukioloaikoja, joten Fonecta Connect näyttää nyt tavalliset perjantain aukioloajat (9-17). Ehdotus: pe 25.12. suljettu.
>
> Voitte hyväksyä yhdellä napautuksella, muokata aikaa tai jättää ehdotuksen väliin. Päätös on aina teidän.

English gloss:

> Hi Furry Paw Vet Clinic! Christmas Day is on Friday 25.12. Last year you were closed that day, but no exception hours have been added this year, so Fonecta Connect now shows your regular Friday hours (09:00-17:00). We suggest: Fri 25.12. closed.
>
> Approve with one tap, edit the hours, or skip it. The decision is always yours.

## 3. Ask instead of guess (low confidence or cold start)

Finnish:

> Hei Furry Paw Vet Clinic! Jouluaatto on torstaina 24.12. Meillä ei ole varmaa tietoa aukioloajoistanne. Oletteko auki jouluaattona 24.12.? Vastaa esimerkiksi 9-13 tai suljettu.

English gloss:

> Hi Furry Paw Vet Clinic! Christmas Eve is on Thursday 24.12. We do not have reliable data on your hours. Are you open on Christmas Eve 24.12.? Reply for example 9-13 or closed.

## 4. No change needed (reliability: we do not invent work)

Finnish:

> Hei Furry Paw Vet Clinic! Isänpäivä on sunnuntaina 8.11. Olette sunnuntaisin normaalisti suljettu, eikä isänpäivä ole arkipyhä, joten aukioloaikoihin ei tarvita muutosta.

English gloss:

> Hi Furry Paw Vet Clinic! Father's Day is on Sunday 8.11. You are normally closed on Sundays and this is not a public holiday, so no change is needed.

## 5. Receipt after apply (hours)

Finnish:

> Kiitos! Jouluaaton aukioloajat 9-13 on nyt tallennettu. Ne näkyvät Googlessa, Apple Mapsissa, Bingissä ja Fonectan palveluissa.

English gloss:

> Done. Christmas Eve hours 9-13 are saved and will show on Google, Fonecta Finder, 020202 and the other channels Connect publishes to.

## 5b. Receipt after apply (closed day, singular)

Finnish:

> Kiitos! Joulupäivän sulkeutuminen on nyt tallennettu. Se näkyy Googlessa, Apple Mapsissa, Bingissä ja Fonectan palveluissa.

English gloss:

> Done. Christmas Day closure is saved and will show on Google, Fonecta Finder, 020202 and the other channels Connect publishes to.

## 5c. Suggestion when a decide link exists (example URL)

Finnish:

> Hei Furry Paw Vet Clinic! Jouluaatto on torstaina 24.12. Viime vuonna olitte auki 9-13, mutta tälle vuodelle ei ole lisätty poikkeusaukioloaikoja, joten Fonecta Connect näyttää nyt tavalliset torstain aukioloajat (9-17). Ehdotus: to 24.12. klo 9-13.
>
> Voitte hyväksyä yhdellä napautuksella, muokata aikaa tai jättää ehdotuksen väliin. Päätös on aina teidän.
> Voitte myös päättää selaimessa: https://kaiku.example/decide/sug-furry-paw-2026-12-24

English gloss:

> Hi Furry Paw Vet Clinic! Christmas Eve is on Thursday 24.12. Last year you were open 09:00-13:00 that day, but no exception hours have been added this year, so Fonecta Connect now shows your regular Thursday hours (09:00-17:00). We suggest: Thu 24.12. 09:00-13:00.
>
> Approve with one tap, edit the hours, or skip it. The decision is always yours.
> You can also decide in the browser: https://kaiku.example/decide/sug-furry-paw-2026-12-24

## 5d. Button for a suggestion we do not know

Finnish:

> En löytänyt ehdotusta, johon tämä vastaus liittyy.

English gloss:

> I could not find the suggestion this reply belongs to.

## 0. Step 1 email (subject, then body)

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
> Last year your hours that day were 9 to 13.
> I suggest your hours on Christmas Eve (24.12.) are 9 to 13.
>
> Approve, edit or decline with one tap, no login needed:
> https://kaiku.example/d/EXAMPLE-TOKEN
>
> Kaiku, Fonecta Connect

## 5e. Standing-permission question after an approval

Finnish:

> Viime vuonna 9-13, tänä vuonna taas 9-13. Tehdäänkö näin joka jouluaatto?

English gloss:

> Last year 9 to 13, this year 9 to 13 again. Want me to do this every Christmas Eve?

## 6. Edit prompt after Edit

Finnish:

> Selvä. Kirjoittakaa uusi aukioloaika vastaamalla tähän viestiin, esimerkiksi "9-13" tai "suljettu".

English gloss:

> Reply with the new hours, like 9-13, or 'closed'.

## 7. Thanks after No thanks

Finnish:

> Selvä, aukioloaikoihin ei tehdä muutoksia. Kiitos vastauksesta! Voitte muuttaa päätöstä milloin tahansa.

English gloss:

> Understood, no changes will be made to your hours. Thanks for replying! You can change your mind any time.

## 8. Reply not understood

Finnish:

> En ymmärtänyt vastausta. Voitte painaa jotakin painikkeista tai kirjoittaa esimerkiksi "9-13" tai "suljettu".

English gloss:

> Sorry, I did not understand that. Tap one of the buttons, or write the hours like 9-13, or 'closed'.
