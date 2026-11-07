#!/usr/bin/env python3
"""Put the Zadarma SIP credentials back on the ElevenLabs trunk and keep the US caller ID header.

Why: on 7 Nov a PATCH of outbound_trunk_config replaced the whole config and dropped the credentials (ElevenLabs treats
that field as a full replacement). Reads ELEVENLABS_API_KEY, ELEVENLABS_PHONE_NUMBER_ID and ZADARMA_SIP_PASSWORD from
/root/hack/kaiku/.env through kaiku.contact.whatsapp.load_env. Prints only statuses, never a secret or a full number.
Usage: /root/hack/kaiku/.venv/bin/python /root/hack/kaiku/tools/trunk_creds.py
"""
from __future__ import annotations

import json
import os
import sys
import urllib.error
import urllib.request

sys.path.insert(0, "/root/hack/kaiku")
from kaiku.contact import whatsapp as W  # noqa: E402

CALLER_ID = "+16465064807"   # the Zadarma account's restored US number, the CallerID on both SIP logins
SIP_USER = "356162"          # Zadarma SIP login ElevenLabsFI


def main() -> int:
    W.load_env()
    key = os.environ.get("ELEVENLABS_API_KEY", "")
    pid = os.environ.get("ELEVENLABS_PHONE_NUMBER_ID", "")
    pw = os.environ.get("ZADARMA_SIP_PASSWORD", "").strip().strip('"')
    if not (key and pid):
        print("ElevenLabs key or phone number id missing in .env"); return 2
    if not pw:
        print("ZADARMA_SIP_PASSWORD not stored; run tools/paste_env.sh ZADARMA_SIP_PASSWORD first"); return 2
    body = {"outbound_trunk_config": {
        "address": "sip.zadarma.com", "transport": "tcp", "media_encryption": "disabled",
        "headers": {"P-Asserted-Identity": f"<sip:{CALLER_ID}@sip.zadarma.com>"},
        "credentials": {"username": SIP_USER, "password": pw}}}
    req = urllib.request.Request(f"https://api.elevenlabs.io/v1/convai/phone-numbers/{pid}",
                                 data=json.dumps(body).encode(), method="PATCH",
                                 headers={"xi-api-key": key, "Content-Type": "application/json"})
    try:
        with urllib.request.urlopen(req, timeout=30) as r:
            d = json.loads(r.read()); st = r.status
    except urllib.error.HTTPError as e:
        print("PATCH failed:", e.code, (e.read() or b"")[:300].decode(errors="replace").replace(pw, "<pw>")); return 1
    ot = d.get("outbound_trunk") or d.get("provider_config") or {}
    print(f"PATCH {st} | auth credentials: {ot.get('has_auth_credentials')} | username: {ot.get('username')} | "
          f"caller id header: {(ot.get('headers') or {}).get('P-Asserted-Identity')}")
    return 0 if ot.get("has_auth_credentials") else 1


if __name__ == "__main__":
    sys.exit(main())
