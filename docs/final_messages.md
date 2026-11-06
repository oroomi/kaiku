# Final customer messages

Demo business: Furry Paw Vet Clinic (fictional Yext sandbox entity). Items 1 to 4 are the exact Suggestion texts from `python3 -m kaiku.suggest.cli --business data/furry_paw.json` (no network): 24.12. hours, 25.12. closed, 24.12. with no history (ask), 8.11. no change. Text as sent over WhatsApp, with English glosses.

## 1. Suggestion with proposed hours (WhatsApp buttons: Hyväksy / Muokkaa / Ei kiitos)

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

> Thank you! The Christmas Eve hours (9 to 13) are now saved. They show on Google, Apple Maps, Bing and Fonecta services.

## 5b. Receipt after apply (closed day, singular)

Finnish:

> Kiitos! Joulupäivän sulkeutuminen on nyt tallennettu. Se näkyy Googlessa, Apple Mapsissa, Bingissä ja Fonectan palveluissa.

English gloss:

> Thank you! The Christmas Day closure is now saved. It shows on Google, Apple Maps, Bing and Fonecta services.

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

## 6. Edit prompt after Muokkaa

Finnish:

> Selvä. Kirjoittakaa uusi aukioloaika vastaamalla tähän viestiin, esimerkiksi "9-13" tai "suljettu".

English gloss:

> Sure. Reply with the new hours, for example "9-13" or "closed".

## 7. Thanks after Ei kiitos

Finnish:

> Selvä, aukioloaikoihin ei tehdä muutoksia. Kiitos vastauksesta! Voitte muuttaa päätöstä milloin tahansa.

English gloss:

> Understood, no changes will be made to your hours. Thanks for replying! You can change your mind any time.

## 8. Reply not understood

Finnish:

> En ymmärtänyt vastausta. Voitte painaa jotakin painikkeista tai kirjoittaa esimerkiksi "9-13" tai "suljettu".

English gloss:

> I did not understand that. Tap one of the buttons or write for example "9-13" or "closed".
