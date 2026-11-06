#!/usr/bin/env python3
"""Captures for the Kaiku submission video (live app). Max 2 chain runs. Never prints the key.
Usage: capture_video.py main | room | aura | voice | reset"""
import os, sys, json, time, shutil, glob, requests
from pathlib import Path
from dotenv import load_dotenv
from playwright.sync_api import sync_playwright
load_dotenv("/root/hack/kaiku/.env")
BASE = "https://kaiku.hankintaviikko.fi"
OUT = Path("/root/hack/kaiku/video/cap"); OUT.mkdir(parents=True, exist_ok=True)
KEY = os.environ.get("KAIKU_ROOM_KEY", "")
CURSOR = """(()=>{const d=document.createElement('div');d.id='__cur';d.style.cssText='position:fixed;z-index:2147483647;pointer-events:none;width:26px;height:26px;border-radius:50%;background:rgba(255,255,255,.9);box-shadow:0 0 0 3px rgba(143,211,232,.7);left:-50px;top:-50px;transition:transform .08s;';
document.addEventListener('DOMContentLoaded',()=>document.body.appendChild(d));
addEventListener('mousemove',e=>{d.style.left=(e.clientX-13)+'px';d.style.top=(e.clientY-13)+'px'},true);
addEventListener('mousedown',()=>d.style.transform='scale(.7)',true);addEventListener('mouseup',()=>d.style.transform='scale(1)',true);})()"""

def move_click(page, sel, steps=25):
    el = page.locator(sel).first; el.scroll_into_view_if_needed(); b = el.bounding_box()
    page.mouse.move(b["x"]+b["width"]/2, b["y"]+b["height"]/2, steps=steps); page.wait_for_timeout(250)
    page.mouse.down(); page.wait_for_timeout(90); page.mouse.up()

def save_video(page, name):
    p = page.video.path(); page.context.close(); shutil.move(p, OUT/f"{name}.webm")

def main():
    marks = {}
    with sync_playwright() as pw:
        br = pw.chromium.launch()
        dctx = br.new_context(viewport={"width":1920,"height":1080}, record_video_dir=str(OUT/"tmp"), record_video_size={"width":1920,"height":1080}, locale="fi-FI")
        dctx.add_init_script(CURSOR)
        d = dctx.new_page(); t0 = time.time(); T = lambda: round(time.time()-t0, 2)
        d.goto(BASE+"/", wait_until="load"); marks["home_loaded"] = T()
        d.wait_for_timeout(4500); marks["idle_end"] = T()
        opts = d.eval_on_selector_all("#date option", "o=>o.map(x=>[x.value,x.textContent])"); marks["date_options"] = opts
        d.select_option("#date", "2026-12-24"); d.wait_for_timeout(700)
        sid = {}
        d.on("response", lambda r: sid.update(json.loads(r.text())) if r.url.endswith("/api/run?business=furry-paw&date=2026-12-24") and r.request.method=="POST" else None)
        marks["before_run"] = T(); move_click(d, "#run"); marks["run_click"] = T()
        d.wait_for_selector("#decide-go:visible", timeout=120000); marks["decide_visible"] = T()
        d.wait_for_timeout(2500)
        sug = requests.get(f"{BASE}/api/suggestions/{sid['suggestion_id']}").json()
        url = sug["decide_url"]; marks["sid"] = sid["suggestion_id"]; marks["rows"] = len(d.query_selector_all("#rows > *"))
        # phone
        pctx = br.new_context(viewport={"width":390,"height":844}, device_scale_factor=2, is_mobile=True, has_touch=True, record_video_dir=str(OUT/"tmp"), record_video_size={"width":390,"height":844}, locale="fi-FI")
        p = pctx.new_page(); pt0 = time.time(); p.goto(url, wait_until="load"); p.wait_for_timeout(3500)
        marks["phone_loaded"] = round(time.time()-pt0,2)
        b = p.locator(".btn.go").first.bounding_box()
        p.touchscreen.tap(b["x"]+b["width"]/2, b["y"]+b["height"]/2); marks["phone_tap"] = round(time.time()-pt0,2)
        p.wait_for_timeout(9000); marks["phone_end"] = round(time.time()-pt0,2)
        p.screenshot(path=str(OUT/"phone_after.png"))
        marks["phone_text"] = p.inner_text("#dc")[:400]
        save_video(p, "phone")
        marks["desktop_applying"] = T()
        # wait for apply/verified headline
        d.wait_for_function("document.body.innerText.includes('9-13') || document.body.innerText.includes('9–13')", timeout=60000)
        marks["desktop_flipped"] = T(); d.wait_for_timeout(9000)
        marks["headline"] = d.inner_text("#headline")[:200]; marks["bigcap"] = d.inner_text("#big-cap")[:200]
        d.screenshot(path=str(OUT/"home_after.png")); marks["after_end"] = T()
        # voice moment, same page
        d.wait_for_timeout(500); marks["voice_start"] = T()
        d.evaluate("window.KaikuVoice.say('Onko eläinlääkäri auki jouluaattona?')")
        d.wait_for_function("document.getElementById('kv-ai').textContent.length>10", timeout=40000)
        d.wait_for_timeout(7000); marks["voice_end"] = T(); marks["voice_ai"] = d.inner_text("#kv-ai")
        d.screenshot(path=str(OUT/"home_voice.png"))
        save_video(d, "desktop")
        br.close()
    json.dump(marks, open(OUT/"marks_main.json","w"), ensure_ascii=False, indent=1); print(json.dumps(marks, ensure_ascii=False, indent=1)[:2500])

def phone2():
    """Second (last) chain run: only to record the decision page at 2x pixel density (video 780x1688)."""
    with sync_playwright() as pw:
        br = pw.chromium.launch()
        r = requests.post(f"{BASE}/api/run", params={"business":"furry-paw","date":"2026-12-24"}).json(); sid = r["suggestion_id"]
        url = None
        for _ in range(60):
            time.sleep(1)
            x = requests.get(f"{BASE}/api/suggestions/{sid}")
            if x.status_code == 200 and x.json().get("decide_url"): url = x.json()["decide_url"]; break
        pctx = br.new_context(viewport={"width":390,"height":844}, device_scale_factor=2, is_mobile=True, has_touch=True, record_video_dir=str(OUT/"tmp"), record_video_size={"width":780,"height":1688}, locale="fi-FI")
        p = pctx.new_page(); pt0 = time.time(); p.goto(url, wait_until="load"); p.wait_for_timeout(5500)
        b = p.locator(".btn.go").first.bounding_box(); marks = {"phone_loaded": round(time.time()-pt0,2)}
        p.touchscreen.tap(b["x"]+b["width"]/2, b["y"]+b["height"]/2); marks["phone_tap"] = round(time.time()-pt0,2)
        p.wait_for_timeout(10000); marks["phone_end"] = round(time.time()-pt0,2); marks["text"] = p.inner_text("#dc")[:300]
        save_video(p, "phone2"); br.close()
    json.dump(marks, open(OUT/"marks_phone2.json","w"), ensure_ascii=False, indent=1); print(marks)

def room():
    import re
    marks = {}
    with sync_playwright() as pw:
        br = pw.chromium.launch()
        ctx = br.new_context(viewport={"width":1920,"height":1080}, record_video_dir=str(OUT/"tmp"), record_video_size={"width":1920,"height":1080}, locale="fi-FI")
        ctx.add_init_script(CURSOR); pg = ctx.new_page(); t0=time.time(); T=lambda: round(time.time()-t0,2)
        requests.get(f"{BASE}/api/room/reset", params={"key": KEY})
        pg.goto(BASE+"/room", wait_until="load"); pg.wait_for_timeout(7000); marks["room_loaded"]=T()
        jars = []
        for i in range(3):
            s = requests.Session(); h = s.get(BASE+"/join").text
            jars.append((s, re.search(r'data-biz="([^"]+)"', h).group(1)))
        marks["biz"] = [b for _, b in jars]
        for (s,b),a in zip(jars, ["10-14", "Suljettu", "9-13"]):
            r = s.post(BASE+"/api/room/answer", json={"business_id": b, "answer": a}); marks.setdefault("answers",[]).append([a, r.status_code, r.json()])
            marks.setdefault("t_ans",[]).append(T()); pg.wait_for_timeout(3800)
        pg.wait_for_timeout(3500); marks["end"]=T()
        pg.screenshot(path=str(OUT/"room_after.png"))
        save_video(pg, "room"); br.close()
    requests.get(f"{BASE}/api/room/reset", params={"key": KEY})
    json.dump(marks, open(OUT/"marks_room.json","w"), ensure_ascii=False, indent=1); print(json.dumps(marks, ensure_ascii=False)[:1500])

def aura():
    with sync_playwright() as pw:
        br = pw.chromium.launch()
        ctx = br.new_context(viewport={"width":1920,"height":1080}, record_video_dir=str(OUT/"tmp"), record_video_size={"width":1920,"height":1080}, locale="fi-FI")
        ctx.add_init_script(CURSOR); pg = ctx.new_page()
        pg.goto(BASE+"/aura", wait_until="load"); pg.wait_for_timeout(36000)
        pg.screenshot(path=str(OUT/"aura.png")); save_video(pg, "aura"); br.close()

def reset():
    r = requests.post(BASE+"/api/reset", headers={"X-Kaiku-Key": KEY}); print(r.status_code, r.text[:300])

if __name__=="__main__":
    {"phone2":phone2,"main":main,"room":room,"aura":aura,"reset":reset}[sys.argv[1]]()
