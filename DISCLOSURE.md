# DISCLOSURE: brought versus built (kept true at all times)

## Built
All application code in this repository was written during the event, after the bell commit e2f7382 (Fri 6 Nov 2026 18:49Z),
with AI coding tools (Claude Code: Fable orchestrating, Sonnet builders and verifiers). Everything not listed under "Brought" is
written after that commit.

## Brought (declared)
- voice-pilot, github.com/oroomi/voice-pilot (our own, MIT, published 18 Oct 2026), vendored under vendor/voice-pilot with its
  licence. The design is reused; the server code was rewritten during the event.
- maplibre-gl 4.7.1, vendored (BSD-3-Clause).
- Map tiles: OpenFreeMap. Map data: OpenStreetMap via Overpass (ODbL).
- Live feeds: Föli SIRI VM, Fintraffic Digitraffic AIS, Open-Meteo (all CC BY 4.0).
- Nager.Date public holidays API; Smart Data Models contexts.
- Services run unmodified: Orion-LD (FIWARE NGSI-LD context broker) and MongoDB, as Docker images.
- Libraries and APIs: mcp Python SDK, Anthropic SDK (model claude-sonnet-5-5), ElevenLabs API (TTS and STT), Yext sandbox API
  (entity provided by Fonecta), Serper (Google places lookup), Meta WhatsApp Cloud API (test number).
- Infrastructure: our VPS, domain, and a Cloudflare tunnel.
- /root/hack/bin scripts (pre-existing process tooling, not product code): deploy, shot, smoke, expose.

## Fictional data
"Furry Paw Vet Clinic" is Fonecta's sandbox business; its history is a labelled sample we wrote.

## GenAI in the product
Claude (suggestion explanations, voice tool loop), ElevenLabs (voice).
