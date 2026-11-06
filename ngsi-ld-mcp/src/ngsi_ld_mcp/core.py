"""Gateway: all behaviour, no MCP imports. The MCP server and the CLI are thin shells around this."""
from __future__ import annotations

import uuid
from datetime import datetime, timezone
from typing import Any

from .broker import Broker, BrokerError, eid
from .config import Config
from .store import ProposalStore


class GateError(Exception):
    """A refusal by the human gate or a bad request. Message is meant to be read by an agent."""


def now() -> str:
    return datetime.now(timezone.utc).strftime("%Y-%m-%dT%H:%M:%S.000Z")


def _prop(value: Any) -> dict:
    return {"type": "Property", "value": value}


def _instances(attr: Any) -> list[dict]:
    if attr is None:
        return []
    return attr if isinstance(attr, list) else [attr]


def _compact_instance(inst: dict) -> dict:
    out: dict[str, Any] = {"datasetId": inst.get("datasetId") or "default"}
    if inst.get("type") == "Relationship":
        out["object"] = inst.get("object")
    else:
        out["value"] = inst.get("value")
    for k in ("observedAt", "unitCode", "modifiedAt"):
        if k in inst:
            out[k] = inst[k]
    meta = {
        k: (v.get("value") if isinstance(v, dict) and "value" in v else v)
        for k, v in inst.items()
        if isinstance(v, dict) and k not in ("value",) and v.get("type") in ("Property", "Relationship")
    }
    if meta:
        out["meta"] = meta
    return out


def compact_entity(ent: dict, include_all: bool = True) -> dict:
    out: dict[str, Any] = {"id": ent.get("id"), "type": ent.get("type")}
    for k, v in ent.items():
        if k in ("id", "type", "@context", "createdAt", "modifiedAt"):
            continue
        insts = [_compact_instance(i) for i in _instances(v) if isinstance(i, dict)]
        if not insts and not isinstance(v, (dict, list)):
            continue
        if not include_all:
            default = [i for i in insts if i["datasetId"] == "default"]
            insts = default[:1] or insts[:1]
            out[k] = insts[0] if insts else None
        else:
            out[k] = insts[0] if len(insts) == 1 and insts[0]["datasetId"] == "default" else insts
    return out


class Gateway:
    def __init__(self, cfg: Config | None = None, broker: Broker | None = None):
        self.cfg = cfg or Config()
        self.broker = broker or Broker(self.cfg)
        self.store = ProposalStore(self.cfg.proposals_path)
        self._native_dataset_writes_unsupported = False

    # ---------- read tools ----------
    async def list_entity_types(self) -> dict:
        r = await self.broker.request("GET", "/types")
        types = (r or {}).get("typeList") if isinstance(r, dict) else r
        return {"types": types or []}

    async def query_entities(self, type: str, q: str | None = None, georel: str | None = None, limit: int = 20,
                             geometry: str | None = None, coordinates: str | None = None,
                             attrs: str | None = None) -> dict:
        limit = max(1, min(int(limit), 200))
        params: dict[str, Any] = {"type": type, "limit": limit, "options": "sysAttrs"}
        if q:
            params["q"] = q
        if georel:
            if not (geometry and coordinates):
                raise GateError("georel needs geometry (e.g. Point) and coordinates (e.g. [24.94,60.17]) as well")
            params.update(georel=georel, geometry=geometry, coordinates=coordinates)
        if attrs:
            params["attrs"] = attrs
        r = await self.broker.request("GET", "/entities", params=params)
        ents = [compact_entity(e, include_all=False) for e in (r or [])]
        return {"count": len(ents), "limit": limit, "entities": ents}

    async def get_entity(self, id: str, include_all_instances: bool = True) -> dict:
        ent = await self.broker.request("GET", f"/entities/{eid(id)}")
        out = compact_entity(ent, include_all=include_all_instances)
        pend = [p["proposal_id"] for p in self.store.all().values() if p["entity_id"] == id and p["status"] == "pending"]
        if pend:
            out["pending_proposals"] = pend
        return out

    async def get_attribute_history(self, id: str, attr: str) -> dict:
        try:
            r = await self.broker.request("GET", f"/temporal/entities/{eid(id)}", params={"attrs": attr})
        except BrokerError as e:
            if e.status in (501, 404, 405):
                return {"supported": False, "reason": f"this broker has no temporal API ({e.status}); "
                        "use get_entity to read the observedAt of each instance, or subscribe() to record changes elsewhere"}
            raise
        return {"supported": True, "history": r}

    # ---------- write plumbing ----------
    async def _write_instance(self, entity_id: str, attr: str, inst: dict) -> None:
        """Create or replace ONE instance (by datasetId) of an attribute, leaving other instances alone."""
        if not inst.get("datasetId"):
            # default instance: POST /attrs overwrites only the default instance, even when others exist
            try:
                await self.broker.request("POST", f"/entities/{eid(entity_id)}/attrs", body={attr: inst})
            except BrokerError as e:
                if e.status in (0, 401, 403, 404):
                    raise
                await self.broker.request("PATCH", f"/entities/{eid(entity_id)}/attrs/{attr}", body=inst)
            return
        if not self._native_dataset_writes_unsupported:
            try:
                await self.broker.request("POST", f"/entities/{eid(entity_id)}/attrs", body={attr: inst})
                return
            except BrokerError as e:
                if e.status != 501:
                    raise
                # Orion-LD builds before full datasetId support answer 501 here (seen on post-v1.12.0)
                self._native_dataset_writes_unsupported = True
        await self._write_dataset_instance_by_recreate(entity_id, attr, inst)

    async def _write_dataset_instance_by_recreate(self, entity_id: str, attr: str, inst: dict) -> None:
        """Fallback for brokers that cannot add a datasetId instance in place: read the entity, replace the
        one instance, delete and re-create the entity. Rolls back to the original on failure."""
        if not self.cfg.recreate_fallback:
            raise GateError("this broker cannot write datasetId instances in place and NGSI_LD_RECREATE_FALLBACK is off")
        path = f"/entities/{eid(entity_id)}"
        orig = await self.broker.request("GET", path)
        insts = [i for i in _instances(orig.get(attr)) if i.get("datasetId") != inst["datasetId"]]
        insts.append(inst)
        new = {**orig, attr: insts if len(insts) > 1 else insts[0]}
        for k in ("createdAt", "modifiedAt", "@context"):
            new.pop(k, None)
        orig_body = {k: v for k, v in orig.items() if k not in ("createdAt", "modifiedAt", "@context")}
        await self.broker.request("DELETE", path)
        try:
            await self.broker.request("POST", "/entities", body=new)
        except BrokerError as e:
            try:
                await self.broker.request("POST", "/entities", body=orig_body)
            except BrokerError as e2:
                raise GateError(f"entity {entity_id} could not be re-created and rollback failed: {e2.message}") from e2
            raise GateError(f"write failed, entity rolled back unchanged: {e.message}") from e

    async def _current_default(self, entity_id: str, attr: str) -> dict | None:
        ent = await self.broker.request("GET", f"/entities/{eid(entity_id)}")
        for i in _instances(ent.get(attr)):
            if not i.get("datasetId"):
                return i
        return None

    # ---------- the human gate ----------
    async def propose_update(self, id: str, attr: str, value: Any, reason: str) -> dict:
        if not reason or not reason.strip():
            raise GateError("a proposal needs a reason a human can read")
        if attr in ("id", "type", "@context"):
            raise GateError(f"'{attr}' is not an updatable attribute")
        cur = await self._current_default(id, attr)  # also proves the entity exists
        # an older pending proposal for the same attr shares the one proposed slot: mark it superseded
        for p in self.store.all().values():
            if p["entity_id"] == id and p["attr"] == attr and p["status"] == "pending":
                p.update(status="superseded", decided_at=now())
                self.store.put(p)
        pid = "prop-" + uuid.uuid4().hex[:10]
        ts = now()
        inst = {
            "type": "Relationship" if (cur or {}).get("type") == "Relationship" else "Property",
            "datasetId": self.cfg.proposed_dataset,
            "observedAt": ts,
            "proposalId": _prop(pid),
            "proposalStatus": _prop("pending"),
            "reason": _prop(reason),
        }
        inst["object" if inst["type"] == "Relationship" else "value"] = value
        await self._write_instance(id, attr, inst)  # NEVER the default instance
        rec = {"proposal_id": pid, "entity_id": id, "attr": attr, "value": value, "reason": reason,
               "base_value": (cur or {}).get("value", (cur or {}).get("object")), "status": "pending",
               "proposed_at": ts, "type": inst["type"], "decided_at": None, "approver": None, "reject_reason": None}
        self.store.put(rec)
        return {"proposal_id": pid, "status": "pending", "entity_id": id, "attr": attr, "proposed_value": value,
                "current_value": rec["base_value"], "note": "default instance NOT changed; a human must approve"}

    def list_proposals(self, status: str | None = "pending") -> dict:
        rows = [p for p in self.store.all().values() if status in (None, "all") or p["status"] == status]
        rows.sort(key=lambda p: p["proposed_at"])
        return {"count": len(rows), "proposals": rows}

    def _pending(self, pid: str) -> dict:
        rec = self.store.get(pid)
        if not rec:
            raise GateError(f"unknown proposal_id {pid}")
        if rec["status"] != "pending":
            raise GateError(f"proposal {pid} is already {rec['status']}")
        return rec

    async def _mark_proposed_instance(self, rec: dict, status: str, who: str | None, note: str | None) -> None:
        inst = {
            "type": rec["type"],
            "datasetId": self.cfg.proposed_dataset,
            "observedAt": now(),
            "proposalId": _prop(rec["proposal_id"]),
            "proposalStatus": _prop(status),
            "reason": _prop(rec["reason"]),
            "decidedBy": _prop(who or ""),
        }
        if note:
            inst["decisionNote"] = _prop(note)
        inst["object" if rec["type"] == "Relationship" else "value"] = rec["value"]
        await self._write_instance(rec["entity_id"], rec["attr"], inst)

    async def approve(self, proposal_id: str, approver: str) -> dict:
        if not approver or not approver.strip():
            raise GateError("approve needs the name of the human approver")
        rec = self._pending(proposal_id)
        cur = await self._current_default(rec["entity_id"], rec["attr"])
        cur_val = (cur or {}).get("value", (cur or {}).get("object"))
        warnings = []
        if cur_val != rec["base_value"]:
            warnings.append(f"default value changed since the proposal ({rec['base_value']!r} -> {cur_val!r})")
        ts = now()
        inst = {
            "type": rec["type"],
            "observedAt": ts,
            "approvedBy": _prop(approver),
            "proposalId": _prop(rec["proposal_id"]),
            "reason": _prop(rec["reason"]),
        }
        inst["object" if rec["type"] == "Relationship" else "value"] = rec["value"]
        await self._write_instance(rec["entity_id"], rec["attr"], inst)  # the ONLY default-instance write
        rec.update(status="approved", approver=approver, decided_at=ts)
        self.store.put(rec)
        try:
            await self._mark_proposed_instance(rec, "approved", approver, None)
        except BrokerError as e:
            warnings.append(f"default written, audit mark on proposed instance failed: {e.message}")
        return {"proposal_id": proposal_id, "status": "approved", "approver": approver, "applied_value": rec["value"],
                "entity_id": rec["entity_id"], "attr": rec["attr"], "warnings": warnings}

    async def reject(self, proposal_id: str, reason: str) -> dict:
        rec = self._pending(proposal_id)
        ts = now()
        rec.update(status="rejected", reject_reason=reason, decided_at=ts)
        self.store.put(rec)
        warnings = []
        try:
            await self._mark_proposed_instance(rec, "rejected", None, reason)
        except BrokerError as e:
            warnings.append(f"audit mark on proposed instance failed: {e.message}")
        return {"proposal_id": proposal_id, "status": "rejected", "reason": reason, "warnings": warnings,
                "note": "default instance untouched"}

    # ---------- subscriptions ----------
    async def subscribe(self, type: str, q: str | None, notify_url: str, description: str = "") -> dict:
        if not notify_url.startswith(("http://", "https://")):
            raise GateError("notify_url must be an http(s) URL")
        sub: dict[str, Any] = {
            "type": "Subscription",
            "description": description or f"ngsi-ld-mcp subscription on {type}",
            "entities": [{"type": type}],
            "notification": {"format": "normalized", "endpoint": {"uri": notify_url, "accept": "application/json"}},
        }
        if q:
            sub["q"] = q
        try:
            await self.broker.request("POST", "/subscriptions", body=sub)
        except BrokerError as e:
            raise GateError(f"subscribe failed: {e.message}") from e
        subs = (await self.list_subscriptions())["subscriptions"]
        mine = [s for s in subs if s.get("uri") == notify_url and s.get("type") == type]
        return {"created": True, "subscription": mine[-1] if mine else None}

    async def list_subscriptions(self) -> dict:
        r = await self.broker.request("GET", "/subscriptions")
        out = []
        for s in r or []:
            out.append({
                "id": s.get("id"), "type": ((s.get("entities") or [{}])[0]).get("type"), "q": s.get("q"),
                "description": s.get("description"), "uri": ((s.get("notification") or {}).get("endpoint") or {}).get("uri"),
                "status": s.get("status") or (s.get("isActive") if "isActive" in s else None),
            })
        return {"count": len(out), "subscriptions": out}

    async def unsubscribe(self, id: str) -> dict:
        await self.broker.request("DELETE", f"/subscriptions/{eid(id)}")
        return {"deleted": id}
