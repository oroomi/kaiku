#!/bin/bash
# Resumable render of the KaikuBody comp (v3 film): one chunk list per scene (<= 192 frames each), so the voice scene is its own chunk range
# (video/build/v3ch/c_voice_*.mp4 : re-render only those when the clip is inserted). Skips finished chunks, concats to build/v3.silent.mp4.
# Env: RENDER_SCALE (0.5 feedback cut; set HALF=false in src/scenes.ts and RENDER_SCALE=1 for the final), RENDER_GL=none, CONC. One render at a time (heavy lock), >= 2500 MB available before each chunk.
cd /root/hack/kaiku/video/remotion; B=/root/.cache/ms-playwright/chromium_headless_shell-1223/chrome-headless-shell-linux64/chrome-headless-shell
export RENDER_GL=none; export RENDER_SCALE=${RENDER_SCALE:-0.5}; CH=${CH:-../build/v3ch}
mkdir -p $CH
node dump_scenes.mjs > /dev/null && cp ../build/scenes.json ../build/v3/scenes.json
python3 - <<'PY' > $CH/plan.txt
import json
sc = json.load(open('/root/hack/kaiku/video/build/v3/scenes.json')); at = 0
for s in sc:
    n = round(s['dur'] * 30); k = 0
    for a in range(0, n, 192):
        b = min(a + 191, n - 1); print(f"c_{s['id']}_{k} {at + a} {at + b}"); k += 1
    at += n
PY
while read name a b; do f=$CH/$name.mp4
  for try in 1 2 3 4; do [ -s $f ] && break
    while [ $(free -m | awk '/^Mem:/{print $7}') -lt 2500 ]; do sleep 20; done
    /root/hack/bin/heavy node render_body.mjs --browser $B --out $f.part.mp4 --frames $a-$b >> $CH/log.txt 2>&1 && mv $f.part.mp4 $f
  done
done < $CH/plan.txt
while read name a b; do [ -s $CH/$name.mp4 ] || { echo INCOMPLETE $name; exit 1; }; done < $CH/plan.txt
awk '{print "file '"'"'" $1 ".mp4'"'"'"}' $CH/plan.txt > $CH/list.txt
ffmpeg -v error -y -f concat -safe 0 -i $CH/list.txt -c copy ../build/v3.silent.mp4 && echo CHUNKS_DONE
