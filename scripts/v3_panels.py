#!/usr/bin/env python3
"""v3 trailer screen pictures -> video/trailer/public/products/kaiku/panels/*.jpg (real captures, see NOTES v3).
email: the real HTML body the ladder's build_message wrote (scratch dry-run .eml), shown in a plain mail frame; host text swapped for the public one, token elided."""
import re, glob, email
from pathlib import Path
from PIL import Image
from playwright.sync_api import sync_playwright
CH = "/root/.cache/ms-playwright/chromium-1223/chrome-linux64/chrome"
C3 = Path("/root/hack/kaiku/video/cap3"); P = Path("/root/hack/kaiku/video/trailer/public/products/kaiku/panels"); P.mkdir(parents=True, exist_ok=True)
f = sorted(glob.glob('/tmp/claude-0/v3/kcopy/data/email_outbox/*.eml'))[-1]
m = email.message_from_binary_file(open(f, 'rb')); subj = m['Subject']
body = [p for p in m.walk() if p.get_content_type() == 'text/html'][0].get_payload(decode=True).decode()
body = re.sub(r'http://127\.0\.0\.1:8282/d/[A-Za-z0-9_-]+', 'https://kaiku.hankintaviikko.fi/d/…', body)
html = f"""<html><body style="margin:0;background:#f4f6f7;font-family:system-ui,sans-serif"><div style="padding:22px 22px 14px;background:#fff;border-bottom:1px solid #dde3e5">
<div style="font-size:12px;color:#667;letter-spacing:.06em">INBOX</div><div style="font-size:21px;font-weight:700;color:#1c2b2d;margin-top:6px;line-height:1.25">{subj}</div>
<div style="font-size:14px;color:#556;margin-top:8px">Kaiku, Fonecta Connect &nbsp;to me</div></div><div style="background:#fff;padding:6px 22px 30px;font-size:17px">{body.replace('<html><body style="font-family:system-ui,sans-serif;font-size:16px;color:#1c2b2d">','<div style="font-size:17px;color:#1c2b2d;line-height:1.5">').replace('</body></html>','</div>')}</div></body></html>"""
with sync_playwright() as pw:
    b = pw.chromium.launch(executable_path=CH); pg = b.new_page(viewport={"width": 390, "height": 760}, device_scale_factor=2)
    pg.set_content(html); pg.wait_for_timeout(400); pg.screenshot(path=str(C3 / "email.png")); b.close()
def crop(src, box, out, size):
    im = Image.open(src).convert("RGB").crop(box); im = im.resize(size, Image.LANCZOS); im.save(P / out, quality=92)
W2 = 2  # panel pictures at 2x of the 380-wide cell
crop(C3 / "chat_c.png", (345, 12, 1085, 12 + int(740 * 718 / 798)), "chat.jpg", (798 * 2, 718 * 2))   # chat panel (2 cells wide)
em = Image.open(C3 / "email.png"); crop(C3 / "email.png", (0, 0, 780, int(780 * 718 / 380)), "email.jpg", (380 * 2, 718 * 2)) if em.size[1] >= int(780 * 718 / 380) else None
if not (P / "email.jpg").exists() or em.size[1] < int(780 * 718 / 380):
    bg = Image.new("RGB", (780, int(780 * 718 / 380)), (244, 246, 247)); bg.paste(em.convert("RGB"), (0, 0)); bg.resize((760, 1436), Image.LANCZOS).save(P / "email.jpg", quality=92)
call = Image.open("/root/hack/kaiku/video/remotion/public/appr_1080/phone_call.png").convert("RGB"); call.resize((760, 1436), Image.LANCZOS).save(P / "call.jpg", quality=92)
cell = (380 * 2, 340 * 2)
crop(C3 / "home_clean.png", (357, 0, 1563, 1080), "home.jpg", cell)           # score arc + cards
crop(C3 / "decide_open.png", (0, 150, 780, 150 + int(780 * 340 / 380)), "decide.jpg", cell)         # the decision page on a phone
crop(C3 / "decide_chq.png", (0, 1688 - int(780 * 340 / 380), 780, 1688), "chq.jpg", cell)             # the reach-you question
crop(C3 / "chat_a.png", (1500, 12, 1500 + 480, 12 + int(480 * 340 / 380)), "listing.jpg", cell) if False else crop(C3 / "chat_c.png", (1085, 12, 1085 + 500, 12 + int(500 * 340 / 380)), "listing.jpg", cell)
print(sorted(x.name for x in P.iterdir()))
