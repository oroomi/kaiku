#!/usr/bin/env python3
"""Screen captures for the approval cut (7 Nov). Read-only: GETs only, no Kaiku server is started, nothing is sent.
Sources (swap these to re-capture on the real page): SRC_STATE1 / SRC_STATE2 = the two approved mock pages (capture-only copies in
video/appr/site/static, MOCK chip removed), served by a plain python http.server on 127.0.0.1:8399; judge = live /judge?key=.
Usage: capture_approval.py A B C D P F G phones   (beats; each -> video/appr/clips/<beat>.mp4 trimmed to beats.json duration)"""
import os, sys, json, time, shutil, subprocess, requests
from pathlib import Path
from dotenv import load_dotenv
from playwright.sync_api import sync_playwright
load_dotenv("/root/hack/kaiku/.env")
ROOT = Path("/root/hack/kaiku/video/appr"); CL = ROOT / "clips"; TMP = CL / "tmp"; TMP.mkdir(parents=True, exist_ok=True)
SITE = "http://127.0.0.1:8399/static/"
SRC_STATE1 = SITE + "mock_a.html"; SRC_STATE2 = SITE + "mock_b.html"
LIVE = "https://kaiku.hankintaviikko.fi"
BEATS = {b["id"]: b for b in json.load(open(ROOT / "beats.json"))["beats"]}

JS = r"""
(()=>{
const st=document.createElement('style');st.textContent=`
html{overflow:hidden;transform-origin:0 0;will-change:transform}
.kv,#kv{display:none!important}
#__cur{position:absolute;z-index:99999;pointer-events:none;width:30px;height:30px;border-radius:50%;background:rgba(255,255,255,.92);box-shadow:0 0 0 4px rgba(143,211,232,.75);transition:left .9s cubic-bezier(.45,0,.2,1),top .9s cubic-bezier(.45,0,.2,1),transform .1s;left:60px;top:60px}
.hl{outline:3px solid #8fd3e8;outline-offset:3px;border-radius:999px;transition:outline-color .3s}
.glowrow{animation:gl 1.6s ease-out 1}@keyframes gl{0%{background:rgba(159,224,181,.0)}25%{background:rgba(159,224,181,.35)}100%{background:rgba(159,224,181,0)}}
.newb{animation:nb .35s cubic-bezier(.2,.8,.2,1) 1}@keyframes nb{from{opacity:0;transform:translateY(14px) scale(.97)}to{opacity:1;transform:none}}
.dots{display:inline-flex;gap:5px;padding:12px 14px}.dots i{width:7px;height:7px;border-radius:50%;background:#8fd3e8;opacity:.4;animation:dd 1s infinite}.dots i:nth-child(2){animation-delay:.15s}.dots i:nth-child(3){animation-delay:.3s}@keyframes dd{50%{opacity:1;transform:translateY(-3px)}}
`;document.head.appendChild(st);
const cur=document.createElement('div');cur.id='__cur';document.body.appendChild(cur);
const H=document.documentElement; let S={x:0,y:0,s:1};
window.cam=(cx,cy,s,ms)=>{S={x:Math.min(0,960-cx*s),y:Math.min(0,540-cy*s),s};H.style.transition=ms?`transform ${ms}ms cubic-bezier(.45,0,.2,1)`:'none';H.style.transform=`translate(${S.x}px,${S.y}px) scale(${S.s})`;};
window.pos=(sel,i)=>{const e=document.querySelectorAll(sel)[i||0];const r=e.getBoundingClientRect();return {x:(r.left-S.x)/S.s,y:(r.top-S.y)/S.s,w:r.width/S.s,h:r.height/S.s,cx:(r.left+r.width/2-S.x)/S.s,cy:(r.top+r.height/2-S.y)/S.s}};
window.curTo=(x,y)=>{cur.style.left=(x-15)+'px';cur.style.top=(y-15)+'px'};
window.curClick=()=>{cur.style.transform='scale(.7)';setTimeout(()=>cur.style.transform='scale(1)',140)};
window.setScore=(f0,f1,ms)=>{const t0=performance.now();const n=document.querySelector('.score-n');const unit=n.querySelector('.score-d');
 const fill=document.getElementById('arc-fill'),dot=document.getElementById('dot'),halo=document.getElementById('dot-halo');
 const ease=t=>t<.5?2*t*t:1-Math.pow(-2*t+2,2)/2;
 const step=()=>{let t=Math.min(1,(performance.now()-t0)/ms);const f=f0+(f1-f0)*ease(t);
  const a=Math.PI*(1-f);const x=220+190*Math.cos(a),y=230-190*Math.sin(a);
  fill.setAttribute('stroke-dashoffset',(1-f).toFixed(3));[dot,halo].forEach(e=>{e.setAttribute('cx',x.toFixed(1));e.setAttribute('cy',y.toFixed(1))});
  n.firstChild.nodeValue=Math.round(f*100);if(t<1)requestAnimationFrame(step)};step()};
window.bubble=(side,text,opts)=>{opts=opts||{};const log=document.getElementById('chat-log');
 const w=document.createElement('div');w.className=(side==='k'?'msg-k':'msg-o')+' newb';const b=document.createElement('div');b.className='b';w.appendChild(b);log.appendChild(w);
 if(opts.dots){b.innerHTML='<span class="dots"><i></i><i></i><i></i></span>';}
 return new Promise(res=>{const go=()=>{b.textContent='';let i=0;const cps=opts.cps||60;const tm=setInterval(()=>{i+=Math.max(1,Math.round(cps/30));b.textContent=text.slice(0,i);if(i>=text.length){clearInterval(tm);res()}},33)};
  if(opts.dots)setTimeout(go,opts.dots);else go()})};
window.flipCard=(i)=>{const c=document.querySelectorAll('.sg')[i];const chip=c.querySelector('.sg-st');chip.textContent='approved';chip.className='mono sg-st st-approved';const a=c.querySelector('.sg-actions');if(a)a.remove();};
})()
"""

def beat(name, url, viewport, fn, dur, mobile=False, cookies=None):
    with sync_playwright() as pw:
        br = pw.chromium.launch()
        w, h = viewport
        ctx = br.new_context(viewport={"width": w, "height": h}, device_scale_factor=2 if mobile else 1, is_mobile=mobile, has_touch=mobile,
                             record_video_dir=str(TMP), record_video_size={"width": w * (2 if mobile else 1), "height": h * (2 if mobile else 1)}, locale="en-US")
        t_create = time.time(); p = ctx.new_page()
        p.goto(url, wait_until="load"); p.wait_for_timeout(1200); p.evaluate(JS)
        fn(p)  # fn schedules itself relative to a T0 returned by start
        br.close() if False else None
        ctx.close(); path = p.video.path(); br.close()
    off = P_OFF.get(name, 0)
    out = CL / f"{name}.mp4"
    subprocess.run(["ffmpeg", "-v", "error", "-y", "-ss", f"{off:.2f}", "-i", path, "-t", f"{dur}", "-r", "30", "-c:v", "libx264", "-crf", "14", "-pix_fmt", "yuv420p", str(out)], check=True)
    Path(path).unlink(missing_ok=True); print(name, "->", out)

P_OFF = {}
class Clock:
    def __init__(s, p, name, t_create_guess=None):
        s.p = p; s.name = name; s.t0 = time.time(); P_OFF[name] = None
    def at(s, t):
        d = t - (time.time() - s.t0)
        if d > 0: s.p.wait_for_timeout(int(d * 1000))
    def run(s, t, js):
        s.at(t); return s.p.evaluate(js)

def mk(name, url, viewport, script, mobile=False):
    mobile_flag = mobile
    """Records, with the page-load lead time measured by wall clock between context creation and T0."""
    dur = BEATS[name]["dur"]
    with sync_playwright() as pw:
        br = pw.chromium.launch()
        w, h = viewport; k = 1
        ctx = br.new_context(viewport={"width": w, "height": h}, device_scale_factor=1, is_mobile=mobile, has_touch=mobile,
                             record_video_dir=str(TMP), record_video_size={"width": w * k, "height": h * k}, locale="en-US")
        if "judge" in url and os.environ.get("KAIKU_ROOM_KEY"):
            pass
        tc = time.time(); p = ctx.new_page()
        p.goto(url, wait_until="load"); p.wait_for_timeout(1500); p.evaluate(JS)
        script.prep(p) if hasattr(script, "prep") else None
        clk = Clock(p, name); off = clk.t0 - tc
        script(p, clk)
        clk.at(dur + 0.3)
        path = p.video.path(); ctx.close(); br.close()
    out = CL / f"{name}.mp4"
    subprocess.run(["ffmpeg", "-v", "error", "-y", "-ss", f"{off:.2f}", "-i", path, "-t", f"{dur}", "-r", "30", "-vf", "scale=%d:%d:flags=lanczos" % (w * 2 if mobile else w, h * 2 if mobile else h), "-c:v", "libx264", "-crf", "14", "-pix_fmt", "yuv420p", str(out)], check=True)
    Path(path).unlink(missing_ok=True); print(name, "->", out, "lead", round(off, 2))

# ---------- scripts per beat ----------
def beatA(p, c):
    p.evaluate("document.querySelector('.score-n').firstChild.nodeValue=0;document.getElementById('arc-fill').setAttribute('stroke-dashoffset',1);window.cam(960,310,1.55,0)")
    c.at(0.15); p.evaluate("setScore(0,0.5,1500);cam(960,310,1.72,3500)")
    c.at(4.6); p.evaluate("document.getElementById('headline').style.transition='text-shadow .6s';document.getElementById('headline').style.textShadow='0 0 28px rgba(143,211,232,.7)'")
    c.at(4.7); p.evaluate("document.querySelectorAll('.checks li.no').forEach((e,i)=>setTimeout(()=>{e.style.transition='transform .3s';e.style.transform='scale(1.25)';setTimeout(()=>e.style.transform='',500)},i*350))")
    c.at(7.4); p.evaluate("cam(960,700,1.45,1300)")

def beatB(p, c):
    p.evaluate("cam(960,700,1.3,0)")
    c.at(0.2); p.evaluate("cam(960,720,1.5,900)")
    btn = lambda i: p.evaluate(f"pos('.sg .sg-actions button',{i})")
    b = [btn(0), btn(1), btn(2)]
    for t, bb, k in ((1.5, b[0], 0), (2.9, b[1], 1), (4.0, b[2], 2)):
        c.at(t); p.evaluate(f"curTo({bb['cx']},{bb['cy']});document.querySelectorAll('.sg .sg-actions button')[{k}].classList.add('hl')")
        c.at(t + 1.1); p.evaluate(f"document.querySelectorAll('.sg .sg-actions button')[{k}].classList.remove('hl')")
    c.at(5.8); p.evaluate("cam(560,720,1.9,1400)")

def beatC(p, c):
    card = p.evaluate("pos('.sg',0)"); acc = p.evaluate("pos('.sg .sg-actions .primary',0)")
    p.evaluate(f"cam({card['cx']},{card['cy']},2.0,0);curTo({acc['cx']-250},{acc['cy']+160})")
    c.at(0.6); p.evaluate(f"curTo({acc['cx']},{acc['cy']})")
    c.at(2.0); p.evaluate("document.querySelectorAll('.sg .sg-actions .primary')[0].classList.add('hl')")
    c.at(2.4); p.evaluate("curClick();flipCard(0)")
    ch = p.evaluate("pos('#chat',0)")
    c.at(3.4); p.evaluate(f"cam({ch['cx']},{ch['y']+300},1.75,900);curTo({ch['cx']+450},{ch['y']+500})")
    c.at(4.0); p.evaluate("window.__b1=bubble('k','Christmas is coming. Do you want to change your hours on Christmas Eve 24.12. to 9-13? Everywhere Connect publishes still says 9-17.',{dots:700,cps:42})")
    c.at(9.1); p.evaluate("bubble('o','yes',{cps:20})")
    c.at(10.3); p.evaluate("bubble('k','Done. 24.12. 9-13 is saved and shows on Google, Fonecta Finder and 020202 within the hour. You changed this last year as well. Do you want to make it recurring, this time of the year?',{dots:600,cps:110})")
    hero = p.evaluate("pos('#hero',0)")
    c.at(11.5); p.evaluate(f"cam({hero['cx']},{hero['cy']},1.7,900)")
    c.at(12.55); p.evaluate("setScore(0.5,0.6,1000);document.getElementById('headline').textContent='Furry Paw Vet Clinic: 3 things to fix before Christmas.'")
    c.at(13.6)
    lst = p.evaluate("pos('#listing',0)")
    p.evaluate(f"cam({lst['cx']},{lst['y']+300},1.75,1000)")
    c.at(14.7); p.evaluate("""(()=>{const dd=[...document.querySelectorAll('.lst dd')][6];dd.innerHTML='24.12. 9-13 <span class="mono soft">· saved 01:31 · Kaiku suggests the Christmas period next</span>';dd.classList.remove('warn');dd.classList.add('glowrow');dd.parentElement.querySelectorAll('dt')[0];})()""")
    c.at(16.4); ch = p.evaluate("pos('#chat',0)"); p.evaluate(f"cam({ch['cx']},{ch['y']+ch['h']-230},1.9,1000)")
    c.at(21.7); p.evaluate("bubble('o','yes, every year',{cps:30})")
    c.at(22.9); p.evaluate("bubble('k','Every Christmas Eve from now on, unless you tell me otherwise. Next: your description has a typo, \"vacination\". Shall I fix it?',{dots:600,cps:100})")
    c.at(23.2); ch = p.evaluate("pos('#chat',0)"); p.evaluate(f"cam({ch['cx']},{ch['y']+ch['h']-200},1.9,900)")

def beatD(p, c):
    # starts in state 2 (mock_b): score 60, chat has the typo question as the last bubble
    ch = p.evaluate("pos('#chat',0)")
    p.evaluate(f"cam({ch['cx']},{ch['y']+ch['h']-230},1.9,0)")
    c.at(2.0); p.evaluate("bubble('o','yes',{cps:20});flipCard(2)")
    c.at(2.7); p.evaluate("bubble('k','Done. Your description now says \"vaccination\".',{dots:500,cps:60})")
    c.at(4.8); rv = p.evaluate("pos('.sg',3)"); p.evaluate(f"cam({rv['cx']},{rv['cy']},1.9,900)")
    c.at(8.6); ch = p.evaluate("pos('#chat',0)"); p.evaluate(f"cam({ch['cx']},{ch['y']+ch['h']-230},1.9,900)")
    c.at(9.2); p.evaluate("bubble('k','A 3-star review has no reply. Shall I post the drafted answer?',{dots:500,cps:45})")
    c.at(10.9); p.evaluate("bubble('o','yes',{cps:20});flipCard(3)")
    c.at(11.7); p.evaluate("bubble('k','Done.',{dots:400,cps:20})")

def beatP(p, c):
    c.at(0.5); p.evaluate("window.scrollTo({top:0})")
    for t, y in ((1.5, 0), (3.0, 700), (5.0, 1500), (7.0, 2250), (9.0, 2900)):
        c.at(t); p.evaluate(f"window.scrollTo({{top:{y},behavior:'smooth'}})")

def beatG(p, c):
    p.evaluate("window.cam(960,300,1.9,0)")
    c.at(0.5); p.evaluate("cam(780,120,2.6,1200)")
    c.at(3.0); p.evaluate("cam(960,500,1.75,1500)")

def run(names):
    for n in names:
        if n == "A": mk("A", SRC_STATE1, (1920, 1080), beatA)
        if n == "B": mk("B", SRC_STATE1, (1920, 1080), beatB)
        if n == "C": mk("C", SRC_STATE1, (1920, 1080), beatC)
        if n == "D": mk("D", SRC_STATE2, (1920, 1080), beatD)
        if n == "P": mk("P", SRC_STATE2, (390, 844), beatP, mobile=True)
        if n == "G": mk("G", LIVE + "/judge?key=" + os.environ["KAIKU_ROOM_KEY"], (1920, 1080), beatG)

# ---------- reliability beat (F): card built from the LIVE /api/feed text (GET) + phone PNGs ----------
def build_F():
    feed = requests.get(LIVE + "/api/feed/furry-paw?date=2026-11-07", timeout=30).json()["suggestions"]
    fd = next(s for s in feed if s["id"].endswith("no_change-2026-11-08"))
    feed2 = requests.get(LIVE + "/api/feed/furry-paw?date=2026-11-07", timeout=30).json()["suggestions"]
    ind = next(s for s in feed2 if s["id"].endswith("no_change-2026-12-06"))
    json.dump({"father": fd, "indep": ind}, open(ROOT / "live_feed_F.json", "w"), indent=1, ensure_ascii=False)
    def card(s, extra=""):
        r = s["reasons"][0]
        return (f'<article class="sg" data-status="info"><div class="sg-top"><span class="mono sg-kind">Holiday check</span><span class="mono sg-st st-approved">no change</span></div>'
                f'<h3>{s["title_en"]}</h3><p class="sg-text">{s["text_en"]}</p>'
                f'<blockquote class="sg-quote" id="why{extra}"><b>Why:</b> {r["text_en"]}</blockquote>'
                f'<div class="sg-meta"><span class="mono sg-conf">{round(s["confidence"]*100)} % sure</span></div><p class="mono sg-src">{r["source"]} · {r["dataset_id"]}</p></article>')
    html = (open(SITE.replace("http://127.0.0.1:8399", str(ROOT / "site")).replace("/static/", "/static/") + "mock_a.html").read())
    head = html.split("<body>")[0]
    body = ('<body><div class="stage" aria-hidden="true"><i class="glow g1"></i><i class="glow g2"></i></div><div class="wrap" style="max-width:760px;margin:0 auto;padding-top:120px">'
            '<section class="w-sug glass"><header class="w-head"><span class="mono">RELIABILITY · LIVE FROM /API/FEED · 7 NOV</span><span class="mono soft">FURRY PAW VET CLINIC (FICTIONAL)</span></header>'
            f'<div class="sug-grid" style="grid-template-columns:1fr" id="f1">{card(fd)}</div><div class="sug-grid" style="grid-template-columns:1fr;margin-top:14px;opacity:0" id="f2">{card(ind,"2")}</div></section></div></body></html>')
    (ROOT / "site/static/mock_F.html").write_text(head + body, encoding="utf-8")
    return fd

def beatF(p, c):
    p.evaluate("""(()=>{const x=document.querySelector('#f1 .sg-text');window.__t=x.innerHTML;document.querySelector('#f1').style.opacity=0;document.querySelector('#f1').style.transition='opacity .6s, transform .6s';document.querySelector('#f1').style.transform='translateY(20px)';
      document.querySelector('#f1 .sg-quote').style.opacity=0;document.querySelector('#f1 .sg-quote').style.transition='opacity .6s';
      document.querySelector('#f2').style.transition='opacity .7s';})()""")
    p.evaluate("cam(960,450,1.85,0)")
    c.at(0.6); p.evaluate("document.querySelector('#f1').style.opacity=1;document.querySelector('#f1').style.transform='none'")
    c.at(4.3); p.evaluate("""(()=>{const x=document.querySelector('#f1 .sg-text');x.innerHTML=x.innerHTML.replace('normally closed on Sundays','<mark style="background:rgba(143,211,232,.28);color:#fff;border-radius:4px;padding:0 3px">normally closed on Sundays</mark>')})()""")
    c.at(6.2); p.evaluate("""(()=>{const x=document.querySelector('#f1 .sg-text');x.innerHTML=x.innerHTML.replace('not a public holiday','<mark style="background:rgba(143,211,232,.28);color:#fff;border-radius:4px;padding:0 3px">not a public holiday</mark>')})()""")
    c.at(8.4); p.evaluate("document.querySelector('#f1 .sg-quote').style.opacity=1;cam(960,460,2.05,1200)")
    c.at(13.5); p.evaluate("document.querySelector('#f2').style.opacity=1;cam(960,500,1.5,1400)")

def build_phones():
    with sync_playwright() as pw:
        br = pw.chromium.launch()
        for n in ("email", "wa", "call"):
            ctx = br.new_context(viewport={"width": 390, "height": 844}, device_scale_factor=2)
            pg = ctx.new_page(); pg.goto(SITE + f"phone_{n}.html"); pg.wait_for_timeout(500); pg.screenshot(path=str(CL / f"phone_{n}.png")); ctx.close()
        br.close()

if __name__ == "__main__" and False: pass

def main():
    names = sys.argv[1:]
    if "F" in names: build_F(); mk("F", SITE + "mock_F.html", (1920, 1080), beatF)
    if "phones" in names: build_phones()
    run([n for n in names if n in "ABCDPG"])
if __name__ == "__main__": main()
