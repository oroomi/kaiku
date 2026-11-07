# Console (`/console?key=<demo key>`)

One phone-width page for the Fonecta Q&A table. Code: `kaiku/console/router.py`, `kaiku/web/templates/console.html`, `kaiku/web/static/console.js`. Same key rule as `/judge`: 403 without the key. Tests: `tests/test_console.py`.

| Block | What it does | Endpoint |
|---|---|---|
| Who Kaiku reaches | A visitor types their own email and phone (international format), Save; "Back to my own" clears it. Shows the masked state, the note that WhatsApp reaches only numbers registered in the Meta test app (email and the call reach anyone), and the last call line (time and ok or reason only) from `data/call_log.jsonl` | `POST/GET/DELETE /api/demo/contact` |
| The customer we were given | Furry Paw Vet Clinic, Vantaa, Fonecta's sandbox entity SinceAI07, fictional; the listing score line and the ON FONECTA NOW panel (what Connect publishes today, read from the Yext sandbox) | `GET /api/score/furry-paw?quick=1`, `GET /api/listing/furry-paw` |
| Run it | Run the chain (24.12.), Reset demo (the visitor's contact stays), a reminder to send "moi" to the WhatsApp test number first (24 hour window), and a link to the live events on `/judge` built in the browser | `POST /api/run`, `POST /api/reset` |

Rules: no full phone number or email is ever in the HTML (`tests/test_console.py`); the page stays silent on test servers like every other page (outbound only from production). Ask the person first, clear their contact after.
