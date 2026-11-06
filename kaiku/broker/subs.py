"""The two standing subscriptions. Idempotent: matched by subscriptionName."""
from __future__ import annotations

import os

SUB_MISSING = "kaiku-holiday-hours-missing"
SUB_DEFAULT = "kaiku-holiday-hours-resolved"


def notify_url() -> str:
    base = os.environ.get("PUBLIC_URL") or "http://127.0.0.1:8210"
    # Orion-LD runs on the host network (see docker-compose.yml), so 127.0.0.1 reaches our app.
    return base.rstrip("/") + "/broker/notify"


def ensure_subscriptions(broker=None, endpoint=None, suffix: str = "") -> dict:
    """(a) holidayHoursStatus -> "missing" (b) holidayHours changes. Returns {name: id}.
    Orion-LD does not apply q to keys inside an object value, so router.py filters again (belt and braces)."""
    from . import get_broker
    b = broker or get_broker()
    url = endpoint or notify_url()
    return {
        SUB_MISSING + suffix: b.create_subscription(SUB_MISSING + suffix, ["holidayHoursStatus"], url,
                                           q='holidayHoursStatus.status=="missing"'),
        SUB_DEFAULT + suffix: b.create_subscription(SUB_DEFAULT + suffix, ["holidayHours"], url),
    }
