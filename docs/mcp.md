# ngsi-ld-mcp in Kaiku

`ngsi-ld-mcp/` is a standalone MCP server (see its README). Kaiku uses it for two things.

## How Kaiku uses it

Status (6 Nov 2026, checked): the package is built and tested standalone. It is NOT mounted in the running app (`/mcp` returns 404, there is no `kaiku/mcp_bridge`) and it is not installed in the app's Python environment, so the voice agent's broker tools are off unless you `pip install ./ngsi-ld-mcp`. The text below describes the intended wiring; the wiring below is the contract Kaiku's voice and chain modules are
built against (the voice builder owns `kaiku/voice/tools.py`, the broker builder owns the notify route). Check those modules for what landed.

- **The voice tool loop.** Kaiku's voice assistant gets the MCP tools as its tool list. When the owner (or a Fonecta judge) asks
  "what hours do we have for Christmas Eve?" the model calls `get_entity` on the business and reads every instance: the live
  default, the source instances (Yext, website, last year) and the proposed one, each with `observedAt`. When Kaiku wants to change
  hours it calls `propose_update(id, "openingHours", value, reason)` with the Finnish reason text; the result is a `proposal_id`
  and the live hours do not change.
- **Decide = approve.** The owner's one tap (WhatsApp link, web card or spoken "yes") ends in `Gateway.approve(proposal_id, owner_name)`
  in the app process, not in the model's hands: the voice session runs with `NGSI_LD_MCP_HIDE_DECISIONS=1`, so the model can
  propose but cannot approve. Reject and "edit" (edit = reject plus a new proposal) work the same way.
- **Detect = subscribe.** `subscribe(type, q, notify_url)` points a broker subscription at Kaiku's `/api/broker/notify`, which is how a
  changed attribute starts the chain (route name is the broker builder's call).
- Mounted in the main app with `mount(app, "/mcp")` so the same tools are reachable by any external MCP client for the demo.

The Yext write never depends on the broker or on this server; when the broker is down the proposal path reports "broker offline"
and Kaiku's fallback keeps the chain alive.

## What did not work

- **mcp 2.x.** `pip install mcp` now installs 2.3 where `FastMCP` is gone (`MCPServer`, different transport API). We pin `mcp>=1.2,<2`.
- **Writing a datasetId instance in place.** The Orion-LD build we run (post-v1.12.0) answers `501 datasetId instances are not
  supported` to `POST /entities/{id}/attrs` and `PATCH /entities/{id}/attrs` when the body has a `datasetId`; `PATCH .../attrs/x?datasetId=`
  gives `400 Unsupported URI parameter`; `POST /entityOperations/upsert` with `options=update` returns `500 attribute without type in
  database`, and without the option `501 Datasets not implemented`. What does work: creating an entity with a multi-instance array,
  deleting one instance with `DELETE .../attrs/x?datasetId=`, and default-instance writes that leave the other instances alone. So
  proposals on this build use read, swap one instance, delete, re-create (with rollback). It is correct but not atomic: the entity
  briefly does not exist, and a subscription on the type may see a delete. A native build removes the fallback automatically.
- **Broker crashes while probing.** While probing PATCH variants the broker dropped the connection once and restarted; we treat
  malformed multi-instance writes as dangerous and only send the shapes above.
- **No temporal history.** `-troe` is not enabled, so `get_attribute_history` returns `supported: false`; Kaiku shows `observedAt` per
  instance instead of a chart.
- **FastMCP error text.** Tool errors reach clients as `Error executing tool X: {json}`; clients must read the JSON after the prefix.
- **Single proposed slot.** All proposals for one attribute share one `datasetId`, so a new proposal supersedes a pending one
  (marked `superseded` in the file). Per-proposal datasetIds would keep history in the broker at the cost of clutter; not done.
