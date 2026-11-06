"""In-memory NGSI-LD broker (just enough), served through httpx.MockTransport.
native_datasets=False mimics Orion-LD post-v1.12.0: 501 on in-place datasetId writes."""
from __future__ import annotations

import json
import copy
import httpx


class FakeBroker:
    def __init__(self, native_datasets: bool = False, temporal: bool = False):
        self.entities: dict[str, dict] = {}
        self.subs: dict[str, dict] = {}
        self.native = native_datasets
        self.temporal = temporal
        self.log: list[tuple[str, str]] = []
        self.transport = httpx.MockTransport(self.handle)
        self._n = 0

    def add(self, ent: dict):
        self.entities[ent["id"]] = copy.deepcopy(ent)

    @staticmethod
    def inst(ent, attr):
        v = ent.get(attr)
        return v if isinstance(v, list) else ([v] if v else [])

    def _resp(self, status, body=None):
        return httpx.Response(status, json=body) if body is not None else httpx.Response(status)

    def handle(self, req: httpx.Request) -> httpx.Response:
        path = req.url.path.split("/ngsi-ld/v1", 1)[1]
        m = req.method
        self.log.append((m, path))
        body = json.loads(req.content) if req.content else None
        if body is not None:
            assert "@context" in (body if isinstance(body, dict) else body[0]), "writes must carry @context"
            if isinstance(body, dict):
                body = {k: v for k, v in body.items() if k != "@context"}
        qp = dict(req.url.params)
        if path == "/types" and m == "GET":
            types = sorted({e["type"] for e in self.entities.values()})
            return self._resp(200, {"id": "urn:x", "type": "EntityTypeList", "typeList": types})
        if path == "/entities" and m == "GET":
            out = [copy.deepcopy(e) for e in self.entities.values() if e["type"] == qp.get("type")]
            if "q" in qp:  # supports only attr==value
                k, v = qp["q"].split("==")
                out = [e for e in out if any(str(i.get("value")) == v.strip('"') for i in self.inst(e, k))]
            return self._resp(200, out[: int(qp.get("limit", 20))])
        if path == "/entities" and m == "POST":
            if body["id"] in self.entities:
                return self._resp(409, {"title": "Already Exists"})
            self.entities[body["id"]] = body
            return self._resp(201)
        if path.startswith("/temporal/"):
            if not self.temporal:
                return self._resp(501, {"title": "TRoE is not enabled"})
            return self._resp(200, {"id": path.rsplit("/", 1)[1], "hours": [{"value": "x", "observedAt": "t"}]})
        if path.startswith("/entities/"):
            rest = path[len("/entities/"):]
            eid, _, sub = rest.partition("/")
            from urllib.parse import unquote
            eid = unquote(eid)
            ent = self.entities.get(eid)
            if ent is None:
                return self._resp(404, {"title": "Entity not found", "detail": eid})
            if sub == "" and m == "GET":
                return self._resp(200, copy.deepcopy(ent))
            if sub == "" and m == "DELETE":
                del self.entities[eid]
                return self._resp(204)
            if sub == "attrs" and m == "POST":
                for attr, inst in body.items():
                    if inst.get("datasetId") and not self.native:
                        return self._resp(501, {"title": "Not Implemented", "detail": "datasetId instances are not supported"})
                    self._set(ent, attr, inst)
                return self._resp(204)
            if sub.startswith("attrs/") and m == "PATCH":
                attr = sub.split("/", 1)[1]
                if attr not in ent:
                    return self._resp(404, {"title": "Attribute Not Found"})
                self._set(ent, attr, body)
                return self._resp(204)
        if path == "/subscriptions" and m == "POST":
            self._n += 1
            sid = f"urn:ngsi-ld:Subscription:{self._n}"
            self.subs[sid] = {**body, "id": sid, "status": "active"}
            return self._resp(201)
        if path == "/subscriptions" and m == "GET":
            return self._resp(200, list(self.subs.values()))
        if path.startswith("/subscriptions/") and m == "DELETE":
            from urllib.parse import unquote
            sid = unquote(path.split("/", 2)[2])
            if sid not in self.subs:
                return self._resp(404, {"title": "Subscription not found"})
            del self.subs[sid]
            return self._resp(204)
        return self._resp(400, {"title": "fake broker: unhandled", "detail": f"{m} {path}"})

    def _set(self, ent, attr, inst):
        ds = inst.get("datasetId")
        insts = [i for i in self.inst(ent, attr) if i.get("datasetId") != ds]
        insts.append(inst)
        ent[attr] = insts if len(insts) > 1 else insts[0]
