#!/bin/bash
# Resumable approval render: 20 frame-range chunks (skips finished ones), then concat to video/build/approval.silent.mp4.
# Why: on the shared 2-core box an OffthreadVideo frame fetch can exceed the delayRender timeout when load spikes; a chunk can be re-run alone.
cd /root/hack/kaiku/video/remotion; B=/root/.cache/ms-playwright/chromium_headless_shell-1223/chrome-headless-shell-linux64/chrome-headless-shell
mkdir -p ../build/apch; N=20; S=196
for i in $(seq 0 $((N-1))); do a=$((i*S)); b=$((a+S-1)); [ $b -gt 3901 ] && b=3901; f=../build/apch/c$i.mp4
  for try in 1 2 3 4 5 6; do [ -s $f ] && break; CONC=2 /root/hack/bin/heavy node render_approval.mjs --browser $B --out $f.part.mp4 --frames $a-$b >> ../build/apch/log.txt 2>&1 && mv $f.part.mp4 $f; done
done
for i in $(seq 0 $((N-1))); do [ -s ../build/apch/c$i.mp4 ] || { echo INCOMPLETE; exit 1; }; done
for i in $(seq 0 $((N-1))); do echo "file 'c$i.mp4'"; done > ../build/apch/list.txt
ffmpeg -v error -y -f concat -safe 0 -i ../build/apch/list.txt -c copy ../build/approval.silent.mp4 && echo CHUNKS_DONE
