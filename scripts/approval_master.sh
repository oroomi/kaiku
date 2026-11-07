#!/bin/bash
# Mux the silent render with the loudness-normalised audio; 1080p master, 720p copy, contact sheet. Usage: approval_master.sh
set -e; cd /root/hack/kaiku/video
ffmpeg -v error -y -i appr/audio_raw.wav -af loudnorm=I=-16:TP=-1.5:LRA=9 -ar 48000 appr/audio.wav
ffmpeg -v error -y -i build/approval.silent.mp4 -i appr/audio.wav -map 0:v -map 1:a -c:v copy -c:a aac -b:a 192k -shortest -movflags +faststart kaiku_approval_cut.mp4
ffmpeg -v error -y -i kaiku_approval_cut.mp4 -vf scale=1280:720 -c:v libx264 -preset slow -crf 24 -pix_fmt yuv420p -c:a aac -b:a 128k -movflags +faststart kaiku_approval_cut_720p.mp4
python3 - <<'PY'
import subprocess, json
from PIL import Image
d = float(subprocess.check_output(["ffprobe","-v","error","-show_entries","format=duration","-of","csv=p=0","kaiku_approval_cut.mp4"]))
ts = [1.0, 3.0, 5.0, 12, 21, 33, 40, 47, 56, 62, 72, 82, 90, 100, 116, 127]
tl = json.load(open("appr/timeline.json")); ts = [t for t in ts if t < d - 0.5]
ims = []
for i, t in enumerate(ts):
    subprocess.run(["ffmpeg","-v","error","-y","-ss",str(t),"-i","kaiku_approval_cut.mp4","-frames:v","1","-vf","scale=480:270","appr/sh_%02d.png" % i], check=True)
    ims.append(Image.open("appr/sh_%02d.png" % i))
W = 4; H = (len(ims) + W - 1) // W; sheet = Image.new("RGB", (480 * W, 270 * H))
for i, im in enumerate(ims): sheet.paste(im, ((i % W) * 480, (i // W) * 270))
sheet.save("approval_sheet.jpg", quality=88)
PY
ls -la kaiku_approval_cut*.mp4 approval_sheet.jpg
