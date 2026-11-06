"""Thin async NGSI-LD client (httpx). Every failure becomes a BrokerError with a readable message."""
from __future__ import annotations

from typing import Any
from urllib.parse import quote

import httpx

from .config import Config

CORE = "https://uri.etsi.org/ngsi-ld/v1/ngsi-ld-core-context.jsonld"
JSONLD = "application/ld+json"


class BrokerError(Exception):
    def __init__(self, status: int, message: str):
        super().__init__(message)
        self.status = status
        self.message = message


class Broker:
    def __init__(self, cfg: Config, transport: httpx.AsyncBaseTransport | None = None):
        self.cfg = cfg
        self.base = cfg.url.rstrip("/") + "/ngsi-ld/v1"
        self._http = httpx.AsyncClient(timeout=cfg.timeout, transport=transport)

    @property
    def context(self) -> str:
        return self.cfg.context or CORE

    def _headers(self, write: bool) -> dict:
        h: dict[str, str] = {}
        if self.cfg.tenant:
            h["NGSILD-Tenant"] = self.cfg.tenant
        if write:
            h["Content-Type"] = JSONLD  # context travels in the body
        else:
            h["Accept"] = "application/json"
            h["Link"] = f'<{self.context}>; rel="http://www.w3.org/ns/json-ld#context"; type="application/ld+json"'
        return h

    async def request(self, method: str, path: str, *, params: dict | None = None, body: Any = None) -> Any:
        write = body is not None
        if write:
            if isinstance(body, dict):
                body = {**body, "@context": self.context}
            elif isinstance(body, list):
                body = [{**b, "@context": self.context} for b in body]
        try:
            r = await self._http.request(method, self.base + path, params=params, json=body, headers=self._headers(write))
        except httpx.HTTPError as e:
            raise BrokerError(0, f"broker unreachable at {self.cfg.url}: {type(e).__name__}") from e
        if r.status_code >= 400:
            detail = ""
            try:
                j = r.json()
                detail = j.get("detail") or j.get("title") or ""
            except Exception:
                detail = r.text[:200]
            raise BrokerError(r.status_code, f"broker said {r.status_code} on {method} {path}: {detail}")
        if not r.content:
            return None
        try:
            return r.json()
        except ValueError:
            return None

    async def close(self) -> None:
        await self._http.aclose()


def eid(entity_id: str) -> str:
    return quote(entity_id, safe=":")
