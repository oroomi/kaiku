"""httpx client for Orion-LD (NGSI-LD v1). Every call has a 3 s timeout."""
from __future__ import annotations

import os
import threading

import httpx

from .fallback import BrokerError, BrokerUnavailable, as_list
from .models import SDM_CONTEXT, dataset_id, now_iso

TIMEOUT = 3.0
_WRITE_LOCK = threading.RLock()
# Orion-LD does not evaluate q against keys inside an object Property value (it notified for
# status "ok" and did not for "missing"), so q is off and router.py filters notifications itself.
USE_Q = os.environ.get("KAIKU_BROKER_USE_Q") == "1"
LINK = f'<{SDM_CONTEXT}>; rel="http://www.w3.org/ns/json-ld#context"; type="application/ld+json"'


def broker_url() -> str:
    return os.environ.get("KAIKU_BROKER_URL", "http://127.0.0.1:1026").rstrip("/")


class OrionClient:
    name = "orion-ld"

    def __init__(self, base: str | None = None):
        self.base = base or broker_url()
        self.http = httpx.Client(timeout=TIMEOUT)

    def status(self) -> str:
        return "orion-ld"

    def alive(self) -> bool:
        try:
            return self.http.get(f"{self.base}/version").status_code == 200
        except httpx.HTTPError:
            return False

    def _req(self, method, path, ok=(200, 201, 204), **kw):
        headers = {"Link": LINK, **kw.pop("headers", {})}
        try:
            r = self.http.request(method, f"{self.base}/ngsi-ld/v1{path}", headers=headers, **kw)
        except httpx.HTTPError as e:
            raise BrokerUnavailable(str(e)) from e
        if r.status_code not in ok:
            raise BrokerError(f"{method} {path} -> {r.status_code} {r.text[:200]}")
        return r

    # ---- entities
    def upsert_entity(self, entity: dict) -> None:
        e = {k: v for k, v in entity.items() if k != "@context"}
        r = self._req("POST", "/entities", ok=(201, 409), json=e, headers={"Content-Type": "application/json"})
        if r.status_code == 409:  # exists: replace the whole entity (simple and deterministic)
            self.delete_entity(e["id"])
            self._req("POST", "/entities", json=e, headers={"Content-Type": "application/json"})

    def get_entity(self, eid: str) -> dict | None:
        r = self._req("GET", f"/entities/{eid}", ok=(200, 404), headers={"Accept": "application/json"})
        return None if r.status_code == 404 else r.json()

    def delete_entity(self, eid: str) -> None:
        self._req("DELETE", f"/entities/{eid}", ok=(204, 404))

    # Orion-LD (post-v1.12.0) accepts datasetId instances only when an entity is CREATED:
    # POST/PATCH /attrs and upsert answer 501. So a multi-instance write is read-modify-write:
    # fetch, merge the instance, DELETE + POST the entity (one creation = one notification
    # carrying every instance). Serialised by a lock; not atomic across processes.
    def _write_instance(self, eid, attr, inst, ds_key):
        with _WRITE_LOCK:
            e = self.get_entity(eid)
            if e is None:
                raise BrokerError(f"entity {eid} not found")
            cur = {i.get("datasetId", ""): i for i in as_list(e.get(attr, [])) if i}
            cur[ds_key] = inst
            e[attr] = list(cur.values()) if len(cur) > 1 else inst
            self.delete_entity(eid)
            self._req("POST", "/entities", json=e, headers={"Content-Type": "application/json"})

    def append_instance(self, eid, attr, value, dataset, observed_at=None) -> None:
        ds = dataset_id(dataset)
        self._write_instance(eid, attr, {"type": "Property", "value": value, "datasetId": ds,
                                         "observedAt": observed_at or now_iso()}, ds)

    def set_default(self, eid, attr, value, observed_at=None) -> None:
        inst = {"type": "Property", "value": value, "observedAt": observed_at or now_iso()}
        e = self.get_entity(eid)
        if e is not None and any(i.get("datasetId") for i in as_list(e.get(attr, [])) if i):
            return self._write_instance(eid, attr, inst, "")
        self._req("POST", f"/entities/{eid}/attrs", json={attr: inst}, headers={"Content-Type": "application/json"})

    def set_status(self, eid, attr, value, observed_at=None) -> None:
        """Plain PATCH of one single-instance attribute (no datasetId), e.g. holidayHoursStatus."""
        inst = {"type": "Property", "value": value, "observedAt": observed_at or now_iso()}
        self._req("PATCH", f"/entities/{eid}/attrs", ok=(204, 207), json={attr: inst},
                  headers={"Content-Type": "application/json"})

    # ---- subscriptions
    def create_subscription(self, name, watched, endpoint, q=None, entity_type="Store") -> str:
        for s in self.list_subscriptions():
            if s.get("subscriptionName") == name:
                if s.get("isActive") is False or s.get("status") == "paused":  # Orion pauses after 3 failed deliveries
                    self._req("PATCH", f"/subscriptions/{s['id']}", json={"isActive": True},
                              headers={"Content-Type": "application/json"})
                return s["id"]
        if callable(endpoint):
            raise BrokerError("callable endpoints are fallback-only")
        body = {"type": "Subscription", "subscriptionName": name, "entities": [{"type": entity_type}],
                "watchedAttributes": list(watched),
                "notification": {"format": "normalized", "endpoint": {"uri": endpoint, "accept": "application/json"}}}
        if q and USE_Q:
            body["q"] = q
        r = self._req("POST", "/subscriptions", json=body, headers={"Content-Type": "application/json"})
        return r.headers.get("Location", "").rsplit("/", 1)[-1] or body.get("id", "")

    def list_subscriptions(self) -> list[dict]:
        return self._req("GET", "/subscriptions", headers={"Accept": "application/json"}).json()

    def delete_subscription(self, sid: str) -> None:
        self._req("DELETE", f"/subscriptions/{sid}", ok=(204, 404))


def instances(entity: dict, attr: str) -> dict:
    """{'lastyear': value, ..., 'default': value} for a multi-instance attribute of get_entity()."""
    from .models import source_of
    return {source_of(i.get("datasetId")): i.get("value") for i in as_list(entity.get(attr, []))}
