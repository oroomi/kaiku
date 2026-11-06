"""Channels Fonecta Connect publishes to. Sources are Fonecta's own pages; see docs/apply.md.
Honesty rule: in the sandbox nothing syncs, so no status ever claims a live sync."""
from __future__ import annotations

SOURCE_URLS = ["https://yrityksille.fonecta.fi", "https://fonectaconnect.fi/"]

# named = the name appears on fonectaconnect.fi; category = only a generic category is named there.
CHANNELS = [
    {"name": "Google (Business Profile, Maps, Search)", "kind": "named"},
    {"name": "Fonecta Caller", "kind": "named"},
    {"name": "Finder", "kind": "named"},
    {"name": "020202 Palvelut", "kind": "named"},
    {"name": "Search engines", "kind": "category"},
    {"name": "Map services", "kind": "category"},
    {"name": "Social media services", "kind": "category"},
    {"name": "AI services", "kind": "category"},
]


def publishers_for(entity: dict | None = None) -> list[dict]:
    return [{"name": c["name"], "kind": c["kind"],
             "status": f"sandbox: written to the entity; in production Connect syncs this to {c['name']}",
             "source": SOURCE_URLS[1]} for c in CHANNELS]
