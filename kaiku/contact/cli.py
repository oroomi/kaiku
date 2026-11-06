"""python -m kaiku.contact.cli send-test | final-messages | init"""
from __future__ import annotations

import json
import sys

from . import messages as M
from . import ladder as L
from . import router as R
from . import whatsapp as W

SAMPLE = {"id": "sg-demo-2026-12-24", "business_id": "SinceAI07", "business_name": "Furry Paw Vet Clinic",
          "holiday_date": "2026-12-24", "holiday_name_fi": "Jouluaatto", "holiday_name_en": "Christmas Eve",
          "kind": "hours", "proposed": [{"start": "09:00", "end": "13:00"}], "confidence": 0.9,
          "last_year_hours": [{"start": "09:00", "end": "13:00"}], "google_now": [{"start": "09:00", "end": "17:00"}],
          "status": "proposed", "channel_log": []}


def send_test() -> int:
    W.load_env()
    c = W.get_client()
    phone = L.owner_phone(SAMPLE)
    if not c.configured:
        print("BLOCKED: WA_TOKEN / WA_PHONE_ID not in .env; nothing sent.")
        return 2
    if not phone:
        print("BLOCKED: OWNER_WHATSAPP not in .env")
        return 2
    s = dict(SAMPLE, channel_log=[])
    L.contact(s, client=c, escalate_s=10**9)
    L.cancel_pending()
    print(json.dumps({"status": s["status"], "channel_log": s["channel_log"]}, ensure_ascii=False, indent=1))
    return 0 if s["status"] == "sent" else 1


def main(argv: list[str]) -> int:
    cmd = argv[1] if len(argv) > 1 else "send-test"
    if cmd == "send-test":
        return send_test()
    if cmd == "final-messages":
        M.all_final_messages(); print("wrote docs/final_messages.md"); return 0
    if cmd == "init":
        R.ensure_verify_token(); print("WA_VERIFY_TOKEN present in .env"); return 0
    print(__doc__); return 1


if __name__ == "__main__":
    sys.exit(main(sys.argv))
