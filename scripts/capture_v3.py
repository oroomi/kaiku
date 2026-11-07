#!/usr/bin/env python3
"""v3 film captures on a SILENT LOCAL COPY (port 8282, in-memory fake Yext, see video/NOTES.md v3). Never the production site.
Usage: capture_v3.py home | chat | decide | stills.   Needs /tmp/claude-0/v3/{launch.py,reset.sh} (scratch launcher)."""
import sys, json, time, shutil, subprocess, requests
from pathlib import Path
from playwright.sync_api import sync_playwright
B = "http://127.0.0.1:8282"; OUT = Path("/root/hack/kaiku/video/cap3"); OUT.mkdir(exist_ok=True, parents=True)
CH = "/root/.cache/ms-playwright/chromium-1223/chrome-linux64/chrome"
CURSOR = """(()=>{const d=document.createElement('div');d.id='__cur';d.style.cssText='position:fixed;z-index:2147483647;pointer-events:none;width:26px;height:26px;border-radius:50%;background:rgba(255,255,255,.9);box-shadow:0 0 0 3px rgba(143,211,232,.7);left:-50px;top:-50px;transition:transform .08s;';
document.addEventListener('DOMContentLoaded',()=>document.body.appendChild(d));
addEventListener('mousemove',e=>{d.style.left=(e.clientX-13)+'px';d.style.top=(e.clientY-13)+'px'},true);
addEventListener('mousedown',()=>d.style.transform='scale(.7)',true);addEventListener('mouseup',()=>d.style.transform='scale(1)',true);})()"""
def DECIDE_TOKEN(sid):
    d = json.load(open("/tmp/claude-0/v3/kcopy/data/decide_tokens.json"))
    return [t for t, r in d.items() if r.get("suggestion_id") == sid][-1]
def reset():
    Path("/tmp/claude-0/v3/noperiod").unlink(missing_ok=True); subprocess.run(["/tmp/claude-0/v3/reset.sh"], check=True)
def click(pg, loc, steps=30):
    el = pg.locator(loc).first; el.scroll_into_view_if_needed(); b = el.bounding_box()
    pg.mouse.move(b["x"]+b["width"]/2, b["y"]+b["height"]/2, steps=steps); pg.wait_for_timeout(300); pg.mouse.down(); pg.wait_for_timeout(90); pg.mouse.up()
def typ(pg, text):
    pg.locator("#msg").click(); pg.wait_for_timeout(250)
    for ch in text: pg.keyboard.type(ch); pg.wait_for_timeout(110)
    pg.wait_for_timeout(350); pg.keyboard.press("Enter")
def save(pg, name):
    p = pg.video.path(); pg.context.close(); shutil.move(p, OUT/f"{name}.webm")
def desk(br, name_dir="tmp"):
    c = br.new_context(viewport={"width":1920,"height":1080}, record_video_dir=str(OUT/name_dir), record_video_size={"width":1920,"height":1080})
    c.add_init_script(CURSOR); return c.new_page()
marks = {}
def main(which):
    reset(); t0 = time.time(); T = lambda: round(time.time()-t0, 2)
    with sync_playwright() as pw:
        br = pw.chromium.launch(executable_path=CH)
        if which == "home":
            pg = desk(br); t0 = time.time(); pg.goto(B+"/owner", wait_until="load"); pg.wait_for_timeout(5200); marks["loaded"] = T()
            pg.mouse.move(1200, 300, steps=20)
            for sel in (".sg:nth-of-type(1) button:has-text('Accept')", ".sg button:has-text('Suggest a change')", ".sg button:has-text('Discard')"):
                try: pg.locator(sel).first.hover(); pg.mouse.move(*[v for v in (0,0)], steps=1) if False else None
                except Exception: pass
                pg.wait_for_timeout(900)
            pg.wait_for_timeout(1200); pg.screenshot(path=str(OUT/"home.png")); marks["end"] = T(); save(pg, "home")
        if which == "chat":
            open("/tmp/claude-0/v3/noperiod", "w").write("1")
            # prep (not filmed): the review and the typo are accepted, the period card hidden by the scratch launcher: Christmas Eve is the one open card
            for sid in ("feed-furry-paw-review-sample-2", "feed-furry-paw-description-typo-fa4631"):
                requests.post(f"{B}/api/suggestions/{sid}/accept", json={"session": "prep"}); 
            pg = desk(br); t0 = time.time(); pg.goto(B+"/owner", wait_until="load"); pg.wait_for_timeout(3800); marks["loaded"] = T()
            click(pg, ".sg:has-text('Christmas Eve') button:has-text('Accept')"); marks["accept"] = T(); pg.wait_for_timeout(1500)
            pg.evaluate("document.querySelector('#chat').scrollIntoView({behavior:'smooth',block:'center'})"); pg.wait_for_timeout(2600); marks["chat_in_view"] = T()
            pg.screenshot(path=str(OUT/"chat_a.png"))
            typ(pg, "yes"); marks["yes1"] = T(); pg.wait_for_timeout(3200); pg.screenshot(path=str(OUT/"chat_b.png"))
            typ(pg, "whatsapp"); marks["wa"] = T(); pg.wait_for_timeout(3600); pg.screenshot(path=str(OUT/"chat_c.png"))
            marks["log"] = pg.inner_text("#chat-log"); save(pg, "chat")
        if which == "voice":  # PLACEHOLDER scene: the orb in its listening state on the owner page (no microphone in this capture); the real voice take replaces it
            pg = desk(br); t0 = time.time(); pg.goto(B+"/owner", wait_until="load"); pg.wait_for_timeout(3500)
            pg.evaluate("document.querySelector('#kv').dataset.state='listening'; const c=document.querySelector('#kv-cap'); c.hidden=false; document.querySelector('#kv-you').textContent='...'")
            pg.mouse.move(1500, 700, steps=10); pg.wait_for_timeout(9000); pg.screenshot(path=str(OUT/"voice.png")); marks["end"] = T(); save(pg, "voice")
        if which == "decide":
            r = requests.post(f"{B}/api/run?business=furry-paw&date=2026-12-24").json(); sid = r["suggestion_id"]; time.sleep(5)
            url = requests.get(f"{B}/api/suggestions/{sid}").json(); print(url.get("channel_log")); url = B + "/d/" + DECIDE_TOKEN(sid)
            c = br.new_context(viewport={"width":390,"height":844}, device_scale_factor=2, is_mobile=True, has_touch=True, record_video_dir=str(OUT/"tmp"), record_video_size={"width":780,"height":1688})
            pg = c.new_page(); t0 = time.time(); pg.goto(url, wait_until="load"); pg.add_style_tag(content="#kv{display:none!important}")  # capture only: the voice orb sits on the Call button at 390 px
            pg.wait_for_timeout(2500); pg.screenshot(path=str(OUT/"decide_open.png"))
            b = pg.locator(".btn.go").first.bounding_box(); pg.touchscreen.tap(b["x"]+b["width"]/2, b["y"]+b["height"]/2); marks["tap"] = T()
            pg.wait_for_selector("#chpref:visible", timeout=40000); pg.wait_for_timeout(800); marks["chq"] = T()
            pg.locator("#chpref").scroll_into_view_if_needed(); pg.wait_for_timeout(1800); pg.screenshot(path=str(OUT/"decide_chq.png"))
            b = pg.locator("[data-channel=whatsapp]").first.bounding_box(); pg.touchscreen.tap(b["x"]+b["width"]/2, b["y"]+b["height"]/2); marks["chq_tap"] = T()
            pg.wait_for_timeout(2500); pg.screenshot(path=str(OUT/"decide_chq_done.png")); marks["text"] = pg.inner_text("body")[:700]; marks["token_url"] = "local"; save(pg, "decide")
        br.close()
    json.dump(marks, open(OUT/f"marks_{which}.json", "w"), indent=1); print(json.dumps(marks, indent=1)[:1500])
main(sys.argv[1])
