"""Fire N answers in parallel at a running server and measure time from POST to the SSE apply event.

Usage: python -m kaiku.map.loadtest [BASE_URL=http://127.0.0.1:8213] [N=20]
Resets the room first and leaves the answers in place (reset again before the pitch).
"""
import asyncio
import json
import sys
import time

import httpx


async def main(base: str, n: int) -> dict:
    async with httpx.AsyncClient(base_url=base, timeout=20) as c:
        await c.get("/api/room/reset")
        biz = [b["id"] for b in (await c.get("/api/room/state")).json()["businesses"] if b["s"] == "unknown"][:n]
        sent, got = {}, {}
        ready = asyncio.Event()

        async def listen():
            async with c.stream("GET", "/api/events", timeout=None) as r:
                async for line in r.aiter_lines():
                    if line.startswith(": connected") or line.startswith("retry"):
                        ready.set()
                    if line.startswith("data:"):
                        e = json.loads(line[5:])
                        if e["step"] == "apply" and e["detail"].get("map") and e["business_id"] in sent \
                                and e["business_id"] not in got:
                            got[e["business_id"]] = time.perf_counter()
                            if len(got) == n:
                                return

        task = asyncio.create_task(listen())
        await asyncio.wait_for(ready.wait(), 5)
        await asyncio.sleep(0.2)

        async def answer(i, bid):
            async with httpx.AsyncClient(base_url=base, timeout=20) as cc:
                sent[bid] = time.perf_counter()
                r = await cc.post("/api/room/answer", json={"business_id": bid, "answer": ["9-13", "10-14", "Suljettu", "Normaalisti"][i % 4]})
                assert r.status_code == 200, r.text

        await asyncio.gather(*(answer(i, b) for i, b in enumerate(biz)))
        try:
            await asyncio.wait_for(task, 10)
        except asyncio.TimeoutError:
            pass
        lat = sorted(round((got[b] - sent[b]) * 1000) for b in got)
        st = (await c.get("/api/room/state")).json()["counts"]
        return {"sent": len(biz), "events_received": len(got), "latency_ms": lat, "max_ms": max(lat) if lat else None,
                "p50_ms": lat[len(lat) // 2] if lat else None, "counts": st}


if __name__ == "__main__":
    base = sys.argv[1] if len(sys.argv) > 1 else "http://127.0.0.1:8213"
    n = int(sys.argv[2]) if len(sys.argv) > 2 else 20
    print(json.dumps(asyncio.run(main(base, n))))
