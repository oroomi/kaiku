# Pitch deck (8 slides, text)

Each slide: what is on it, the one sentence said aloud, and where every number comes from. Numbers checked on 7 Nov 2026 about 11:25Z against the live product and EVAL.md. Live frames come from https://kaiku.hankintaviikko.fi; the demo clock is set to 17.12.2026 and the business is the **fictional** Furry Paw Vet Clinic (Fonecta sandbox entity SinceAI07).

## 1. The closed door
On screen: a Google-style result for a vet, "Open 9-17" on 24.12., and a person at a locked door.
Say: Customers forget one-off changes like holiday hours, search results go out of date, and people turn up when the business is closed.

## 2. The chain in one picture
On screen: Detect, Suggest, Contact, Decide, Apply as five boxes with the Orion-LD broker underneath (diagram from the README).
Say: Connect suggests, the customer approves: five steps, no login, and the customer has the last word.

## 3. The owner's side, live
On screen: the owner page. The listing score (a percentage, 40 % and "3 of 7 checks" at the time of writing, `GET /api/score/furry-paw`; it moves with the sandbox), cards with Accept, Suggest a change and Discard, the empty chat that answers once the owner acts, and the Yext read-back after a decision. Then the contact ladder: the plain-words email, the WhatsApp message with Accept and Discard buttons, and the phone call by Kaiku (ElevenLabs, voice Aurora, English). The closing question on every channel, "how would you like to be reached next time", is stored and re-orders the ladder. The promise in every receipt: "We'll update your information everywhere." The /console page is how a Fonecta representative tries it on their own phone.
Say: One tap saves, a typed reply carries the actual hours, and we read the change back from Yext.

## 4. Reliability
On screen: two rows. 8.11. Father's Day: "no change needed" (not a public holiday, the vet is closed on Sundays). A cold-start business: one question and no guess (confidence 0.50, below the 0.6 gate).
Say: Kaiku does not invent work, and below 0.6 confidence it asks instead of guessing. Every proposal carries its reason, and nothing is written until the owner says yes or taps Accept.

## 5. Learning
On screen: an edit to 10-14 becomes the next proposal at confidence 0.9 or more; two declines turn it into no change; the recurring question after an approval (asked only when last year's data exists), and the standing permission it stores.
Say: The second suggestion is better than the first, and recurring changes can get standing permission. (Once granted, the next run for that holiday is applied without asking and the owner is told afterwards.)

## 6. The FIWARE spine
On screen: one Store entity, one attribute `holidayHours`, one datasetId per source (lastyear, website, google, peers, proposed) and the default instance. Subscriptions fire Detect and Decide. Aura: live Turku ships and weather as entities (41 ships, 156 buses, 1 weather station on 7 Nov 11:22Z, `GET /api/aura/status`; the numbers move); ngsi-ld-mcp: agents propose, humans approve.
Say: One business, many sources, one truth, and every source keeps its own provenance.

## 7. What we measured (honest)
On screen: 10 hand-made cases, wrong-suggestion rate 0.0, abstain rate 0.2; the words "self-consistency, not accuracy". 454 tests passing, 7 live-sending tests skipped unless `KAIKU_LIVE=1`. Fonecta gave no dataset format or sample, so `/eval` lets you drop your own file and see every suggestion with its reason and hit rate.
Say: We have not seen Fonecta's data. The backtest has a pluggable loader and prints machine-readable output, ready for your scoring script.

## 8. What is next
On screen: review replies and automatic posts on the same loop (the page already drafts a reply to a sample review and corrects a typo in the description); production sources (Connect's exception-hours history, Google Business Profile, category peers from the customer base); the contact ladder email, then WhatsApp, then a call (the call was answered, approved and written to Yext on 6 Nov, and placed again on 7 Nov at 10:23Z); an 8-week pilot (PILOT.md).
Say: Same loop, more use cases. Scan the QR code and try the cold-start question on your own phone.
