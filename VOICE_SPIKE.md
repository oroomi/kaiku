# Kaiku voice spike (6 Nov 2026)

## Status
- Step 1 Zadarma number: BLOCKED. https://my.zadarma.com/ redirects to https://my.zadarma.com/auth/ (login wall). No number bought, no SIP creds. Cost EUR 0.
- Step 2 ElevenLabs agent: BLOCKED. Key in /root/hack/jx2026/.env lacks permissions convai_read, convai_write, voices_read (401 missing_permissions on agents, phone-numbers, conversations, voices, user). Voice id from that env was therefore not verified for Finnish.
- Step 3 SIP trunk number: BLOCKED (no number, no agent).
- Step 4 test call: not attempted. No call made, no cost.
- Step 5 Meta developers: LOGGED IN. Apps list visible (Motoex Varaukset, Fables Failed Founder). Nothing created.

## Ready payload
/root/hack/kaiku/agent_payload.json (Finnish prompt, dynamic variables, voice id and eleven_flash_v2_5 filled in). Create with:

curl -X POST https://api.elevenlabs.io/v1/convai/agents/create -H "xi-api-key: ${ELEVENLABS_API_KEY}" -H "Content-Type: application/json" -d @/root/hack/kaiku/agent_payload.json
-> store .agent_id as ELEVENLABS_AGENT_ID_KAIKU

## Step 3 (placeholders, check docs if rejected)
curl -X POST https://api.elevenlabs.io/v1/convai/phone-numbers -H "xi-api-key: ${ELEVENLABS_API_KEY}" -H "Content-Type: application/json" -d '{"provider":"sip_trunk","label":"Kaiku FI","phone_number":"${KAIKU_PHONE_NUMBER}","outbound_trunk_config":{"address":"${ZADARMA_SIP_SERVER}","transport":"udp","credentials":{"username":"${ZADARMA_SIP_ID}","password":"${ZADARMA_SIP_PASSWORD}"}}}'
-> store .phone_number_id as ELEVENLABS_PHONE_NUMBER_ID_KAIKU

## Step 4
curl -X POST https://api.elevenlabs.io/v1/convai/sip-trunk/outbound-call -H "xi-api-key: ${ELEVENLABS_API_KEY}" -H "Content-Type: application/json" -d '{"agent_id":"${ELEVENLABS_AGENT_ID_KAIKU}","agent_phone_number_id":"${ELEVENLABS_PHONE_NUMBER_ID_KAIKU}","to_number":"+358451291684","conversation_initiation_client_data":{"dynamic_variables":{"business_name":"Furry Paw Vet Clinic","holiday_name":"jouluaatto","holiday_date":"torstaina 24.12.","last_year_hours":"9-13","google_shows_now":"9-17","proposed_hours":"9-13"}}}'
Then GET /v1/convai/conversations/{conversation_id}.

## Open problems
1. Zadarma login needed (Dayo logs in on the laptop Chrome).
2. ElevenLabs key needs convai_read/convai_write (and voices_read) enabled, or a new full-access key.
