# Pitch deck (8 slides, text)

Each slide: a title, what is on it, and the one sentence said aloud. Live demo frames come from the running app.

## 1. The closed door
On screen: a Google result for a vet, "Open 9-17" on 24 December, and a person at a locked door.
Say: Customers forget one-off changes like holiday hours, search results go out of date, and people turn up when the business is closed.

## 2. The chain in one picture
On screen: Detect, Suggest, Contact, Decide, Apply as five boxes with the Orion-LD broker underneath (diagram from README).
Say: Connect suggests, the customer approves: five steps, no login, and the customer has the last word.

## 3. Live demo frames
On screen: three screenshots. The home headline (Connect 9-17, Kaiku 9-13) and the event strip; the phone decision page with Hyväksy, Muokkaa, Ei kiitos (Approve, Edit, No thanks); the Yext read-back saying verified.
Say: This is the real app on a phone: one tap writes to the team's Yext entity and we read it back.

## 4. Reliability
On screen: two rows. 8.11. Isänpäivä: "no change needed" (not a public holiday, vet closed on Sundays). A cold-start business: one question, no guess.
Say: Kaiku does not invent work, and below 0.6 confidence it asks instead of guessing.

## 5. Learning
On screen: an edit to 10-14 becomes the next proposal at confidence 0.9 or more; two declines turn it into no change; a "standing permission" tick.
Say: The second suggestion is better than the first, and recurring changes can get standing permission.

## 6. The FIWARE spine
On screen: one Store entity, one attribute `holidayHours`, five datasetIds (lastyear, website, google, peers, proposed) and the default instance. Subscriptions fire Detect and Decide. Aura: live Turku buses and ships as entities; ngsi-ld-mcp: agents propose, humans approve.
Say: One business, many sources, one truth, and every source keeps its own provenance.

## 7. What we measured (honest)
On screen: 10 hand-made cases, wrong-suggestion rate 0.0, abstain rate 0.2; the words "self-consistency, not accuracy". 173 tests passing offline.
Say: We have not seen Fonecta's data yet. The backtest has a pluggable loader and prints machine-readable output, ready for your scoring script.

## 8. What is next
On screen: review replies and automatic posts on the same loop; production sources (Connect's exception-hours history, Google Business Profile, category peers from the customer base); the Finnish call lane (in progress); an 8-week pilot (PILOT.md).
Say: Same loop, more use cases. Scan the QR code and approve a suggestion on your own phone.
