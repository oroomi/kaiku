"""In-memory broker with the same interface as client.OrionClient. Used when Orion-LD is unreachable."""
from __future__ import annotations

import copy
import re
import threading
import uuid

import httpx

from .models import dataset_id, now_iso


class BrokerError(Exception):
    pass


class BrokerUnavailable(BrokerError):
    pass


def as_list(v):
    """Orion returns one instance as an object and several as an array."""
    return v if isinstance(v, list) else [v]


_Q = re.compile(r'^\s*(\w+)(?:\.|\[)(\w+)\]?\s*==\s*"?([^"]*)"?\s*$')


def q_matches(q: str | None, attrs: dict) -> bool:
    """Tiny evaluator for q=attr.key=="val" / attr[key]=="val" (all the fallback needs)."""
    if not q:
        return True
    m = _Q.match(q)
    if not m:
        return True
    attr, key, want = m.groups()
    for inst in as_list(attrs.get(attr, [])):
        v = inst.get("value") if isinstance(inst, dict) else None
        if isinstance(v, dict) and str(v.get(key)) == want:
            return True
    return False


class FallbackBroker:
    name = "fallback"

    def __init__(self):
        self._lock = threading.RLock()
        self._ents: dict[str, dict] = {}   # id -> {"type": t, "attrs": {attr: {datasetId|"": instance}}}
        self._subs: dict[str, dict] = {}

    def status(self) -> str:
        return "fallback"

    # ---- entities
    def upsert_entity(self, entity: dict) -> None:
        with self._lock:
            eid = entity["id"]
            rec = self._ents.setdefault(eid, {"type": entity["type"], "attrs": {}})
            changed = {}
            for k, v in entity.items():
                if k in ("id", "type", "@context"):
                    continue
                insts = {}
                for inst in as_list(v):
                    insts[inst.get("datasetId", "")] = copy.deepcopy(inst)
                rec["attrs"][k] = insts
                changed[k] = list(insts.values())
            self._fire(eid, changed)

    def get_entity(self, eid: str) -> dict | None:
        with self._lock:
            rec = self._ents.get(eid)
            if rec is None:
                return None
            out = {"id": eid, "type": rec["type"]}
            for k, insts in rec["attrs"].items():
                lst = [copy.deepcopy(i) for i in insts.values()]
                out[k] = lst[0] if len(lst) == 1 else lst
            return out

    def delete_entity(self, eid: str) -> None:
        with self._lock:
            self._ents.pop(eid, None)

    def _put(self, eid, attr, inst, dataset):
        rec = self._ents.get(eid)
        if rec is None:
            raise BrokerError(f"entity {eid} not found")
        rec["attrs"].setdefault(attr, {})[dataset or ""] = inst
        self._fire(eid, {attr: [inst]})

    def append_instance(self, eid, attr, value, dataset, observed_at=None) -> None:
        ds = dataset_id(dataset)
        inst = {"type": "Property", "value": value, "datasetId": ds, "observedAt": observed_at or now_iso()}
        with self._lock:
            self._put(eid, attr, inst, ds)

    def set_default(self, eid, attr, value, observed_at=None) -> None:
        inst = {"type": "Property", "value": value, "observedAt": observed_at or now_iso()}
        with self._lock:
            self._put(eid, attr, inst, None)

    # ---- subscriptions
    def create_subscription(self, name, watched, endpoint, q=None, entity_type="Store") -> str:
        """endpoint: URL string or in-process callable(notification_dict). Idempotent by name."""
        with self._lock:
            for sid, s in self._subs.items():
                if s["name"] == name:
                    return sid
            sid = f"urn:ngsi-ld:subscription:{uuid.uuid4()}"
            self._subs[sid] = {"id": sid, "name": name, "watched": list(watched), "q": q,
                               "endpoint": endpoint, "type": entity_type}
            return sid

    def list_subscriptions(self) -> list[dict]:
        with self._lock:
            return [{"id": s["id"], "subscriptionName": s["name"], "watchedAttributes": s["watched"], "q": s["q"],
                     "notification": {"endpoint": {"uri": s["endpoint"] if isinstance(s["endpoint"], str) else "callback"}}}
                    for s in self._subs.values()]

    def delete_subscription(self, sid: str) -> None:
        with self._lock:
            self._subs.pop(sid, None)

    # ---- evaluation + delivery
    def _fire(self, eid, changed: dict):
        rec = self._ents[eid]
        for s in list(self._subs.values()):
            if s["type"] != rec["type"]:
                continue
            hit = [a for a in s["watched"] if a in changed]
            if not hit:
                continue
            if not q_matches(s["q"], {a: changed[a] for a in hit}):
                continue
            data = {"id": eid, "type": rec["type"]}
            for a in hit:
                lst = changed[a]
                data[a] = lst[0] if len(lst) == 1 else lst
            note = {"id": f"urn:ngsi-ld:Notification:{uuid.uuid4()}", "type": "Notification",
                    "subscriptionId": s["id"], "notifiedAt": now_iso(), "data": [data]}
            self._deliver(s["endpoint"], note)

    @staticmethod
    def _deliver(endpoint, note):
        try:
            if callable(endpoint):
                endpoint(note)
            else:
                httpx.post(endpoint, json=note, timeout=2.0, headers={"Content-Type": "application/json"})
        except Exception:
            pass  # a dead receiver never breaks a write
