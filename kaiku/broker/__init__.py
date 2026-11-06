"""Kaiku broker layer. `get_broker()` returns Orion-LD when reachable, else the in-memory fallback."""
from __future__ import annotations

import logging
import threading

import httpx

from .client import OrionClient
from .fallback import BrokerError, BrokerUnavailable, FallbackBroker

log = logging.getLogger("kaiku.broker")
__all__ = ["get_broker", "reset_broker", "BrokerError", "BrokerUnavailable"]


class AutoBroker:
    """Delegates to Orion-LD; on the first transport failure switches to the fallback for good
    (state is NOT migrated back, a restart or reset_broker() re-probes)."""

    def __init__(self):
        self._fb = FallbackBroker()
        self._orion = OrionClient()
        self._lock = threading.Lock()
        self.using_fallback = not self._orion.alive()
        self.fallback_reason = "unreachable at start" if self.using_fallback else ""
        if self.using_fallback:
            log.warning("Orion-LD unreachable at %s, using in-memory fallback", self._orion.base)

    @property
    def name(self):
        return "fallback" if self.using_fallback else "orion-ld"

    def status(self) -> str:
        return self.name

    def _call(self, method, *a, **kw):
        if not self.using_fallback:
            try:
                return getattr(self._orion, method)(*a, **kw)
            except BrokerUnavailable as e:
                with self._lock:
                    self.using_fallback, self.fallback_reason = True, str(e)[:120]
                log.warning("Orion-LD went away (%s), switching to fallback", e)
        return getattr(self._fb, method)(*a, **kw)

    def upsert_entity(self, *a, **k): return self._call("upsert_entity", *a, **k)
    def get_entity(self, *a, **k): return self._call("get_entity", *a, **k)
    def delete_entity(self, *a, **k): return self._call("delete_entity", *a, **k)
    def append_instance(self, *a, **k): return self._call("append_instance", *a, **k)
    def set_default(self, *a, **k): return self._call("set_default", *a, **k)
    def create_subscription(self, *a, **k): return self._call("create_subscription", *a, **k)
    def list_subscriptions(self, *a, **k): return self._call("list_subscriptions", *a, **k)
    def delete_subscription(self, *a, **k): return self._call("delete_subscription", *a, **k)


_broker: AutoBroker | None = None
_lock = threading.Lock()


def get_broker() -> AutoBroker:
    global _broker
    with _lock:
        if _broker is None:
            _broker = AutoBroker()
        return _broker


def reset_broker() -> None:
    global _broker
    with _lock:
        _broker = None
