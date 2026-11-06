from __future__ import annotations

import os
from dataclasses import dataclass, field

PROPOSED_DATASET = "urn:ngsi-ld:dataset:kaiku:proposed"


@dataclass
class Config:
    url: str = field(default_factory=lambda: os.environ.get("NGSI_LD_URL", "http://127.0.0.1:1026"))
    context: str | None = field(default_factory=lambda: os.environ.get("NGSI_LD_CONTEXT") or None)
    tenant: str | None = field(default_factory=lambda: os.environ.get("NGSI_LD_TENANT") or None)
    proposals_path: str = field(
        default_factory=lambda: os.environ.get("NGSI_LD_PROPOSALS", os.path.expanduser("~/.ngsi-ld-mcp/proposals.json"))
    )
    proposed_dataset: str = field(default_factory=lambda: os.environ.get("NGSI_LD_PROPOSED_DATASET", PROPOSED_DATASET))
    # Set NGSI_LD_MCP_HIDE_DECISIONS=1 to keep approve/reject OUT of the agent's tool list.
    # Humans then decide through the CLI or the Python API (Gateway.approve).
    hide_decisions: bool = field(default_factory=lambda: os.environ.get("NGSI_LD_MCP_HIDE_DECISIONS", "") in ("1", "true", "yes"))
    # Brokers that answer 501 to in-place datasetId writes get a read-modify-write recreate of the entity.
    recreate_fallback: bool = field(default_factory=lambda: os.environ.get("NGSI_LD_RECREATE_FALLBACK", "1") not in ("0", "false", "no"))
    timeout: float = 10.0
