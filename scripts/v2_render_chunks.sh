#!/bin/bash
# Resumable render of the KaikuBody comp (v2 film): 18 chunks of 192 frames (3456 body frames), skips finished chunks,
# concats to video/build/v2.silent.mp4. Env: RENDER_SCALE (0.5 for the feedback cut), RENDER_GL=none, CONC.
# Why chunks: on this 2-vCPU box one long render dies on memory or a delayRender timeout; a chunk costs minutes, not the film.
cd /root/hack/kaiku/video/remotion; B=/root/.cache/ms-playwright/chromium_headless_shell-1223/chrome-headless-shell-linux64/chrome-headless-shell
mkdir -p ../build/v2ch; N=18; S=192; T=3456
for i in $(seq 0 $((N-1))); do a=$((i*S)); b=$((a+S-1)); [ $b -gt $((T-1)) ] && b=$((T-1)); f=../build/v2ch/c$i.mp4
  for try in 1 2 3 4; do [ -s $f ] && break; /root/hack/bin/heavy node render_body.mjs --browser $B --out $f.part.mp4 --frames $a-$b >> ../build/v2ch/log.txt 2>&1 && mv $f.part.mp4 $f; done
done
for i in $(seq 0 $((N-1))); do [ -s ../build/v2ch/c$i.mp4 ] || { echo INCOMPLETE; exit 1; }; done
for i in $(seq 0 $((N-1))); do echo "file 'c$i.mp4'"; done > ../build/v2ch/list.txt
ffmpeg -v error -y -f concat -safe 0 -i ../build/v2ch/list.txt -c copy ../build/v2.silent.mp4 && echo CHUNKS_DONE
