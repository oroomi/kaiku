"""python -m kaiku.broker.smoke : prove the chain's spine with Orion-LD, then again with the fallback."""
from __future__ import annotations

import json
import os
import sys
import threading
import time
from http.server import BaseHTTPRequestHandler, HTTPServer

from . import client as client_mod
from . import reset_broker, get_broker
from .client import instances
from .models import SOURCES, business_to_entity, furry_paw, hours_value, entity_id
from .router import handle_notification
from .subs import ensure_subscriptions

PORT = 8299
EID = "urn:ngsi-ld:Store:furry-paw-smoke"
DATE = "2026-12-24"
RECV: list = []


class _H(BaseHTTPRequestHandler):
    def do_POST(self):
        body = json.loads(self.rfile.read(int(self.headers.get("content-length", 0))) or b"{}")
        RECV.append(body)
        self.send_response(204)  # Orion-LD pauses a subscription after 3 replies without Content-Length / non-204
        self.end_headers()

    def log_message(self, *a):
        pass


def _wait(n, t=6.0):
    end = time.time() + t
    while len(RECV) < n and time.time() < end:
        time.sleep(0.1)
    return len(RECV) >= n


def run(label: str) -> bool:
    reset_broker()
    b = get_broker()
    print(f"\n=== {label}: broker.status() = {b.status()}")
    RECV.clear()
    b.delete_entity(EID)
    biz = furry_paw()
    biz.id = "furry-paw-smoke"
    b.upsert_entity(business_to_entity(biz, status={"date": DATE, "status": "applied"}))
    subs = ensure_subscriptions(b, f"http://127.0.0.1:{PORT}/broker/notify", suffix="-smoke")
    again = ensure_subscriptions(b, f"http://127.0.0.1:{PORT}/broker/notify", suffix="-smoke")
    print(f"subscriptions: {len(subs)} created, idempotent re-run -> same ids: {subs == again}")

    # three source instances (one attribute, three datasetIds)
    b.append_instance(EID, "holidayHours", hours_value(DATE, "closed"), "lastyear", "2025-12-24T08:00:00.000Z")
    b.append_instance(EID, "holidayHours", hours_value(DATE, [{"start": "09:00", "end": "13:00"}]), "google")
    b.append_instance(EID, "holidayHours", hours_value(DATE, [{"start": "09:00", "end": "13:00"}]), "proposed")
    time.sleep(1.0)
    base = len(RECV)
    RECV[:] = []  # source-instance writes may notify (subscription b); the router ignores non-default instances

    # 1) status -> missing: the subscription must fire
    b.set_default(EID, "holidayHoursStatus", {"date": DATE, "status": "missing"})
    ok1 = _wait(1)
    fired1 = [f for n in RECV for f in handle_notification(n) if f["kind"] == "missing"]
    print(f"DETECT: notification arrived={ok1}, router parsed: {fired1}")

    # 2) owner approves: default instance written -> second notification
    RECV.clear()
    b.set_default(EID, "holidayHours", hours_value(DATE, [{"start": "09:00", "end": "13:00"}]))
    b.set_default(EID, "holidayHoursStatus", {"date": DATE, "status": "approved"})
    ok2 = _wait(1)
    fired2 = [f for n in RECV for f in handle_notification(n) if f["kind"] == "resolved"]
    print(f"DECIDE: notification arrived={ok2}, router parsed: {fired2}")

    e = b.get_entity(EID)
    inst = instances(e, "holidayHours")
    print("one business, instances of holidayHours:")
    for k, v in inst.items():
        print(f"   {k:9s} {json.dumps(v['hours'] if isinstance(v, dict) else v)}")
    ok = ok1 and ok2 and bool(fired1) and bool(fired2) and {"lastyear", "google", "proposed", "default"} <= set(inst)
    for sid in subs.values():
        b.delete_subscription(sid)
    b.delete_entity(EID)
    print(f"RESULT {label}: {'PASS' if ok else 'FAIL'}")
    return ok


def main() -> int:
    srv = HTTPServer(("127.0.0.1", PORT), _H)
    threading.Thread(target=srv.serve_forever, daemon=True).start()
    print(f"temporary receiver on 127.0.0.1:{PORT} pid={os.getpid()} (in-process, stops with the script)")
    url = os.environ.get("KAIKU_BROKER_URL", "http://127.0.0.1:1026")
    results = {}
    results["orion-ld"] = run(f"Orion-LD at {url}")
    os.environ["KAIKU_BROKER_URL"] = "http://127.0.0.1:1"   # dead port
    results["fallback"] = run("dead broker URL (http://127.0.0.1:1)")
    os.environ["KAIKU_BROKER_URL"] = url
    srv.shutdown()
    print("\nSUMMARY", json.dumps(results))
    return 0 if all(results.values()) else 1


if __name__ == "__main__":
    sys.exit(main())
