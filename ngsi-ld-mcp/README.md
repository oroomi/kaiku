# ngsi-ld-mcp

An MCP server that lets an AI agent discover, query and act on an NGSI-LD context broker (FIWARE Orion-LD),
with a **human approval gate on every write**.

Agents propose. Humans approve. The broker holds both, as two instances of one attribute, so the audit trail is the broker itself.

## Quickstart (60 seconds)

```bash
# 1. a broker (any NGSI-LD broker; Orion-LD shown)
docker run -d --name mongo mongo:4.4 --nojournal
docker run -d --name orion --link mongo -p 1026:1026 fiware/orion-ld -dbhost mongo

# 2. the server (stdio)
pip install ngsi-ld-mcp          # or: uvx ngsi-ld-mcp   /   pip install -e . from this folder
NGSI_LD_URL=http://127.0.0.1:1026 python -m ngsi_ld_mcp
```

Claude Desktop (`claude_desktop_config.json`) or Claude Code (`.mcp.json`):

```json
{
  "mcpServers": {
    "ngsi-ld": {
      "command": "uvx",
      "args": ["ngsi-ld-mcp"],
      "env": {
        "NGSI_LD_URL": "http://127.0.0.1:1026",
        "NGSI_LD_PROPOSALS": "/home/me/.ngsi-ld-mcp/proposals.json"
      }
    }
  }
}
```

Claude Code one-liner: `claude mcp add ngsi-ld -e NGSI_LD_URL=http://127.0.0.1:1026 -- python -m ngsi_ld_mcp`

Then ask: "Which entity types are in the broker?", "Propose closing the clinic on 24.12. and tell me the proposal id."

## Tools

| Tool | What it does |
|---|---|
| `list_entity_types()` | types present in the broker |
| `query_entities(type, q=None, georel=None, limit=20, geometry=None, coordinates=None, attrs=None)` | NGSI-LD query; default instance of each attribute |
| `get_entity(id, include_all_instances=True)` | every datasetId instance of multi-instance attributes, each with `observedAt` |
| `get_attribute_history(id, attr)` | temporal API if the broker has one, else `supported: false` with the reason |
| `propose_update(id, attr, value, reason)` | writes a **proposed** instance (`datasetId urn:ngsi-ld:dataset:kaiku:proposed`), returns `proposal_id`. Never touches the live value |
| `list_proposals(status="pending")` | proposals (pending, approved, rejected, superseded, all) |
| `approve(proposal_id, approver)` | the only call that writes the live (default) instance; records who approved |
| `reject(proposal_id, reason)` | closes the proposal, live value untouched |
| `subscribe(type, q, notify_url, description)` / `list_subscriptions()` / `unsubscribe(id)` | broker subscriptions |

Resources: `ngsi-ld://types`, `ngsi-ld://entity/{id}`. Every tool returns compact JSON. Errors are explicit: the MCP result has
`isError: true` and a JSON body such as `{"error":"refused","message":"proposal prop-x is already approved"}` or
`{"error":"broker","status":404,...}`.

## Configuration

| Env | Default | |
|---|---|---|
| `NGSI_LD_URL` | `http://127.0.0.1:1026` | broker base URL |
| `NGSI_LD_CONTEXT` | core context | `@context` URL sent as Link header (reads) and in bodies (writes) |
| `NGSI_LD_TENANT` | none | `NGSILD-Tenant` header |
| `NGSI_LD_PROPOSALS` | `~/.ngsi-ld-mcp/proposals.json` | proposal state file (atomic writes, survives restarts) |
| `NGSI_LD_PROPOSED_DATASET` | `urn:ngsi-ld:dataset:kaiku:proposed` | datasetId of proposed instances |
| `NGSI_LD_MCP_HIDE_DECISIONS` | off | `1` removes `approve`/`reject` from the agent's tool list; humans use the CLI or `Gateway.approve` |
| `NGSI_LD_RECREATE_FALLBACK` | on | see "Broker compatibility" |

Human CLI (never goes through the agent): `python -m ngsi_ld_mcp proposals`, `... approve prop-ab12 --approver Dayo`, `... reject prop-ab12 --reason "wrong day"`.

HTTP: `python -m ngsi_ld_mcp http --port 8765` (streamable HTTP at `/mcp`), or mount into FastAPI:

```python
from ngsi_ld_mcp import mount
mount(app, "/mcp")        # endpoint: /mcp/
```

## The human approval model (safety model)

```
 agent --propose_update--> broker: hours = [ default: "9-17"            <- live, what the world sees
                                             proposed: "9-13" + reason  <- datasetId ...:kaiku:proposed ]
 human --approve(id, "Dayo")--> default := "9-13", approvedBy=Dayo, proposalId=...
                                proposed instance marked approved, decidedBy=Dayo
```

1. `propose_update` can only create or replace the **proposed** instance. There is no code path from it to the default instance.
2. `approve` is the only function that writes the default instance. It needs a named approver, refuses unknown or already decided proposals, and warns if the live value changed since the proposal was made.
3. The broker holds both instances of the same attribute (NGSI-LD multi-attribute with `datasetId`). Anyone reading the entity sees
   the live value, the pending suggestion, its reason, the approver, and every `observedAt`. No second database to trust.
4. Proposal state lives in a JSON file so a restart cannot lose or silently approve anything.
5. Two ways to keep the agent out of the decision: leave `approve` visible and let the MCP client ask the human to confirm that tool call
   (it is marked `destructiveHint`), or set `NGSI_LD_MCP_HIDE_DECISIONS=1` so only a human UI/CLI can approve.

## Broker compatibility (honest notes)

Tested on Orion-LD `post-v1.12.0` (build of Sep 2026). That build answers `501 datasetId instances are not supported` to
`POST/PATCH /entities/{id}/attrs` when the body carries a `datasetId`, though it stores and returns multi-instance attributes fine
(`POST /entities` with an array, `DELETE .../attrs/x?datasetId=`, and default-instance `POST/PATCH` all work). So on that build a proposed
instance is added by read, replace-one-instance, delete and re-create of the entity, with rollback to the original if the re-create fails.
Brokers with native support are used natively (the server tries the native call first and falls back only on a 501). Set
`NGSI_LD_RECREATE_FALLBACK=0` to forbid the fallback. Temporal history needs Orion-LD started with `-troe`; without it `get_attribute_history`
says `supported: false`.

## Tests

`pip install -e ".[test]" && pytest` runs fake-broker tests for every tool (both broker behaviours) and live tests against
`127.0.0.1:1026` that skip themselves when no broker answers (they create `urn:ngsi-ld:Test:mcp-1`, propose, approve, verify, clean up).

## FIWARE Open Innovation Award

Challenge 6: an MCP server on an NGSI-LD broker so agents can discover, query and act on live data, with humans approving every action.

- **Integration.** Speaks plain NGSI-LD v1.6 REST to any broker: entities, types, subscriptions, temporal, `datasetId`, `observedAt`, Link-header contexts, multi-tenancy. Verified against a running Orion-LD. Standard MCP over stdio and streamable HTTP, so Claude Desktop, Claude Code and any MCP client work unchanged.
- **Technical.** Small (about 600 lines), typed, async, 56 tests with a fake broker that reproduces a real Orion-LD limitation, plus live tests. Atomic persistence, rollback on failed writes, stale-value warning, explicit errors.
- **Innovation.** The approval state is not bolted on: the pending suggestion and the live value are two `datasetId` instances of one attribute, so the broker is the audit log, subscriptions fire on the proposal (detect), and a human tap turns it into the live value (decide).
- **Practical.** Used by Kaiku, our Since AI 2026 entry, where a voice assistant proposes holiday opening hours for a business and the owner approves with one tap before anything is published. The same pattern fits any city, building or agri dataset where an agent must not write alone.

## Licence

MIT. Built at Since AI 2026 by The Mishakin Group.
