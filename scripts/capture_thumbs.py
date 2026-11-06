#!/usr/bin/env python3
"""Card thumbnails for the Kaiku trailer: crops of the REAL /room map (DSF 2), centred on each business's dot.
Three answered dots (green) give the lat/lon -> pixel fit. Resets the room before and after (key from .env, never printed)."""
import os, json, time, requests, re
import numpy as np
from PIL import Image
from dotenv import load_dotenv
from playwright.sync_api import sync_playwright
load_dotenv("/root/hack/kaiku/.env")
BASE="https://kaiku.hankintaviikko.fi"; KEY=os.environ["KAIKU_ROOM_KEY"]
OUT="/root/hack/kits/demo-video/krock_recreate/public/products/kaiku/thumbs"; os.makedirs(OUT,exist_ok=True)
RAW="/root/hack/kaiku/video/cap/room_map_raw.png"
biz=requests.get(BASE+"/api/room/state").json()["businesses"][:12]
json.dump(biz,open("/root/hack/kaiku/video/cap/cards_biz.json","w"),ensure_ascii=False)
requests.get(BASE+"/api/room/reset",params={"key":KEY})
jars=[]
for i in range(3):
    s=requests.Session(); h=s.get(BASE+"/join").text; jars.append((s,re.search(r'data-biz="([^"]+)"',h).group(1)))
for (s,b),a in zip(jars,["10-14","Suljettu","9-13"]): print(s.post(BASE+"/api/room/answer",json={"business_id":b,"answer":a}).status_code)
with sync_playwright() as pw:
    br=pw.chromium.launch(); ctx=br.new_context(viewport={"width":1920,"height":1080},device_scale_factor=2,locale="fi-FI")
    pg=ctx.new_page(); pg.goto(BASE+"/room",wait_until="load"); pg.wait_for_timeout(9000)
    pg.mouse.move(1344,583)
    for _ in range(6): pg.mouse.wheel(0,-240); pg.wait_for_timeout(250)
    pg.wait_for_timeout(6000); pg.screenshot(path=RAW); br.close()
requests.get(BASE+"/api/room/reset",params={"key":KEY})
print(jars)
