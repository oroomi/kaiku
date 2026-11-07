#!/usr/bin/env python3
"""Record the /city demo: fly-in, idle, 8 room answers through the real API (each a new visitor), the dots turning
green from Orion-LD notifications. Playwright 1920x1080 headless (SwiftShader WebGL) -> ffmpeg H.264, 20 fps.

Two modes. --mode frames (default): SwiftShader on this 2-core box renders ~1-4 fps, so the page runs on Playwright's
virtual clock (page.clock) and is stepped 40 ms per frame, one screenshot per frame, 25 fps out. Every frame is the real
page; the room answers, Orion-LD notifications and SSE are real and happen in wall time while frames render, so the
vehicles (whose broker positions refresh in wall time) move faster than real life in the film.
--mode realtime: Playwright's record_video_dir, for a machine with a GPU.

Usage: /usr/bin/python3 bin/record_city.py [--base http://127.0.0.1:8230] [--out /root/hack/shots/city_demo.mp4] [--size 1920x1080]
Run against a TEST server (PUBLIC_URL=http://127.0.0.1:82xx). Room answers are demo data and labelled so on the page.
"""
import argparse
import http.cookiejar
import json
import re
import shutil
import subprocess
import sys
import tempfile
import time
import urllib.request
from pathlib import Path

from playwright.sync_api import sync_playwright

ARGS = ["--use-gl=angle", "--use-angle=swiftshader", "--enable-unsafe-swiftshader", "--ignore-gpu-blocklist"]
ANSWERS = ["10-14", "9-13", "closed", "12-16", "10-15", "9-12", "11-15", "closed"]


def room_answer(base: str, answer: str) -> dict:
    """One visitor: GET /join (new cookie jar), then POST /api/room/answer for the business /join assigned."""
    jar = http.cookiejar.CookieJar()
    op = urllib.request.build_opener(urllib.request.HTTPCookieProcessor(jar))
    html = op.open(base + "/join", timeout=10).read().decode()
    m = re.search(r"osm-[nwr]\d+", html)
    if not m:
        return {"ok": False, "error": "no business assigned"}
    req = urllib.request.Request(base + "/api/room/answer", data=json.dumps({"business_id": m[0], "answer": answer}).encode(),
                                 headers={"Content-Type": "application/json"}, method="POST")
    try:
        return json.loads(op.open(req, timeout=10).read())
    except urllib.error.HTTPError as e:
        return {"ok": False, "status": e.code, "body": e.read()[:200].decode(errors="replace")}


def frames_mode(a, w, h, tmp: Path) -> dict:
    import threading
    fps = 20
    step = 1000 // fps
    with sync_playwright() as p:
        browser = p.chromium.launch(args=ARGS)
        page = browser.new_page(viewport={"width": w, "height": h})
        errors = []
        page.on("pageerror", lambda e: errors.append(str(e)))
        page.clock.install()
        sep = "&" if "?" in a.path else "?"
        page.goto(a.base + a.path + sep + "hold=1", wait_until="load", timeout=60000)
        page.wait_for_function("window.__city && window.__city.ready", timeout=120000)
        # pause first, then let the globe tiles arrive in wall time (pausing after a natural run hung the first screenshot)
        page.clock.pause_at(int(time.time() * 1000) + 1000)
        page.wait_for_timeout(4000)
        page.evaluate("window.__city.start()")
        plan = {int((18 + 2 * i) * 1000): ans for i, ans in enumerate(ANSWERS)}  # virtual ms -> answer
        end_ms = 18000 + 2000 * len(ANSWERS) + 10000
        results, threads, t, n = [], [], 0, 0
        while t <= end_ms:
            for at in [k for k in plan if k <= t]:
                ans = plan.pop(at)
                th = threading.Thread(target=lambda x=ans: results.append(room_answer(a.base, x)))
                th.start()
                threads.append(th)
            page.clock.run_for(step)
            page.screenshot(path=str(tmp / f"f{n:05d}.jpg"), type="jpeg", quality=88, timeout=120000)
            t += step
            n += 1
            if n % 100 == 0:
                print(f"frame {n} virtual {t / 1000:.1f}s", flush=True)
        for th in threads:
            th.join()
        approved = page.evaluate("document.getElementById('c-approved').textContent")
        events = page.evaluate("[...document.querySelectorAll('#c-events li')].map(l=>l.textContent)")
        browser.close()
    out = Path(a.out)
    subprocess.run(["ffmpeg", "-y", "-loglevel", "error", "-framerate", str(fps), "-i", str(tmp / "f%05d.jpg"), "-c:v", "libx264",
                    "-crf", "23", "-preset", "medium", "-pix_fmt", "yuv420p", "-movflags", "+faststart", str(out)], check=True)
    return {"frames": n, "fps_out": fps, "approved_counter": approved, "event_lines": events, "page_errors": errors,
            "answers_ok": sum(1 for r in results if r.get("ok")), "answers": results}


def main() -> int:
    ap = argparse.ArgumentParser()
    ap.add_argument("--base", default="http://127.0.0.1:8230")
    ap.add_argument("--out", default="/root/hack/shots/city_demo.mp4")
    ap.add_argument("--size", default="1920x1080")
    ap.add_argument("--path", default="/city?room=1")
    ap.add_argument("--mode", choices=["frames", "realtime"], default="frames")
    a = ap.parse_args()
    w, h = (int(x) for x in a.size.split("x"))
    tmp = Path(tempfile.mkdtemp(prefix="city-rec-"))
    t_start = time.time()
    Path(a.out).parent.mkdir(parents=True, exist_ok=True)
    if a.mode == "frames":
        info = frames_mode(a, w, h, tmp)
        out = Path(a.out)
        dur = subprocess.run(["ffprobe", "-v", "error", "-show_entries", "format=duration", "-of", "csv=p=0", str(out)],
                             capture_output=True, text=True).stdout.strip()
        shutil.rmtree(tmp, ignore_errors=True)
        print(json.dumps({"out": str(out), "mode": "frames (virtual clock)", "duration_s": float(dur or 0),
                          "size_mb": round(out.stat().st_size / 1e6, 2), **info, "wall_s": round(time.time() - t_start)},
                         ensure_ascii=False, indent=1))
        return 0
    with sync_playwright() as p:
        browser = p.chromium.launch(args=ARGS)
        ctx = browser.new_context(viewport={"width": w, "height": h}, record_video_dir=str(tmp),
                                  record_video_size={"width": w, "height": h})
        page = ctx.new_page()
        page.add_init_script("""window.__fps={n:0,t0:0};(function f(t){if(!window.__fps.t0)window.__fps.t0=t;window.__fps.n++;requestAnimationFrame(f)})(0);""")
        errors = []
        page.on("pageerror", lambda e: errors.append(str(e)))
        page.goto(a.base + a.path, wait_until="load", timeout=30000)
        page.wait_for_timeout(12000)   # the fly-in
        page.wait_for_timeout(6000)    # idle drift
        results = []
        for ans in ANSWERS:
            r = room_answer(a.base, ans)
            results.append(r)
            print("answer", ans, r, flush=True)
            page.wait_for_timeout(2000)
        page.wait_for_timeout(10000)
        fps = page.evaluate("(()=>{const f=window.__fps;return f.n/((performance.now()-f.t0)/1000)})()")
        approved = page.evaluate("document.getElementById('c-approved').textContent")
        events = page.evaluate("[...document.querySelectorAll('#c-events li')].map(l=>l.textContent)")
        vid = page.video.path()
        ctx.close()
        browser.close()
    out = Path(a.out)
    out.parent.mkdir(parents=True, exist_ok=True)
    subprocess.run(["ffmpeg", "-y", "-loglevel", "error", "-i", str(vid), "-c:v", "libx264", "-crf", "23", "-preset", "medium",
                    "-pix_fmt", "yuv420p", "-movflags", "+faststart", str(out)], check=True)
    dur = subprocess.run(["ffprobe", "-v", "error", "-show_entries", "format=duration", "-of", "csv=p=0", str(out)],
                         capture_output=True, text=True).stdout.strip()
    shutil.rmtree(tmp, ignore_errors=True)
    print(json.dumps({"out": str(out), "duration_s": float(dur or 0), "size_mb": round(out.stat().st_size / 1e6, 2),
                      "page_fps": round(fps, 1), "approved_counter": approved, "event_lines": events,
                      "answers_ok": sum(1 for r in results if r.get("ok")), "page_errors": errors,
                      "wall_s": round(time.time() - t_start)}, ensure_ascii=False, indent=1))
    return 0


if __name__ == "__main__":
    sys.exit(main())
