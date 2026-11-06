# Vendored: voice-pilot

- Source: /root/hack/kits/voice-pilot (github.com/oroomi/voice-pilot, our own library)
- Licence: MIT (see LICENSE, kept unchanged)
- Date vendored: 2026-11-06 (Since AI 2026 build weekend)
- Status: **pre-existing code brought in** (declared in DISCLOSURE.md). Not written during the event.
- Omitted from the copy to keep the repo small: screenshots, GIFs, recordings, test output, server-node/, node_modules.
- Kaiku's own voice layer (kaiku/voice/*, kaiku/web/static/voice.js, voice.css) was written during the event. It reuses the kit's
  design (data-pilot targets, spotlight, push to talk, captions, ElevenLabs proxy with cache) but not its files at runtime.
