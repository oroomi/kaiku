"""python -m ngsi_ld_mcp            -> stdio MCP server
   python -m ngsi_ld_mcp http      -> streamable HTTP on --port (default 8765)
   python -m ngsi_ld_mcp proposals | approve ID --approver NAME | reject ID --reason TEXT   (human CLI)"""
from __future__ import annotations

import argparse
import asyncio
import json
import sys

from .config import Config
from .core import GateError, Gateway
from .broker import BrokerError
from .server import build_server


def main(argv: list[str] | None = None) -> int:
    ap = argparse.ArgumentParser(prog="ngsi-ld-mcp")
    sub = ap.add_subparsers(dest="cmd")
    h = sub.add_parser("http", help="serve streamable HTTP")
    h.add_argument("--port", type=int, default=8765)
    h.add_argument("--host", default="127.0.0.1")
    sub.add_parser("stdio", help="serve over stdio (default)")
    sub.add_parser("proposals", help="list pending proposals")
    a = sub.add_parser("approve", help="human approval of a proposal")
    a.add_argument("proposal_id")
    a.add_argument("--approver", required=True)
    r = sub.add_parser("reject", help="human rejection of a proposal")
    r.add_argument("proposal_id")
    r.add_argument("--reason", required=True)
    args = ap.parse_args(argv)
    cfg = Config()

    if args.cmd in ("proposals", "approve", "reject"):
        gw = Gateway(cfg)
        try:
            if args.cmd == "proposals":
                out = gw.list_proposals("pending")
            elif args.cmd == "approve":
                out = asyncio.run(gw.approve(args.proposal_id, args.approver))
            else:
                out = asyncio.run(gw.reject(args.proposal_id, args.reason))
        except (GateError, BrokerError) as e:
            print(json.dumps({"error": str(e)}), file=sys.stderr)
            return 1
        print(json.dumps(out, indent=1, ensure_ascii=False))
        return 0

    if args.cmd == "http":
        server = build_server(cfg=cfg, streamable_path="/mcp", open_hosts=False)
        server.settings.host, server.settings.port = args.host, args.port
        server.run(transport="streamable-http")
        return 0
    build_server(cfg=cfg).run(transport="stdio")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
