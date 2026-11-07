#!/bin/bash
# v3 master: audio (score_v3.py -> loudnorm I=-16 TP=-1.5) muxed with build/v3.silent.mp4 in ONE encode (never stream-copy across timebases),
# -> video/kaiku_v3_feedback.mp4, video/kaiku_v3_sheet.jpg (20 frames, 4 columns), stills every 15 s in /tmp/claude-0/v3_review/.
set -e; cd /root/hack/kaiku/video; A=build/v3/audio; NAME=${1:-kaiku_v3_feedback}
python3 ../scripts/score_v3.py
M=$(nice ffmpeg -hide_banner -nostats -i $A/audio_raw.wav -af loudnorm=I=-16:TP=-1.5:LRA=11:print_format=json -f null - 2>&1 | sed -n '/^{/,/^}/p')
g() { echo "$M" | python3 -c "import sys,json;print(json.load(sys.stdin)['$1'])"; }
nice ffmpeg -y -v error -i $A/audio_raw.wav -af "loudnorm=I=-16:TP=-1.5:LRA=11:measured_I=$(g input_i):measured_TP=$(g input_tp):measured_LRA=$(g input_lra):measured_thresh=$(g input_thresh):offset=$(g target_offset):linear=true,alimiter=limit=0.84:level=disabled" -ar 48000 $A/audio_master.wav
nice ffmpeg -y -v error -i build/v3.silent.mp4 -i $A/audio_master.wav -map 0:v -map 1:a -c:v libx264 -preset slow -crf 17 -pix_fmt yuv420p -c:a aac -b:a 192k -ar 48000 -shortest -movflags +faststart $NAME.mp4
D=$(ffprobe -v error -show_entries format=duration -of csv=p=0 $NAME.mp4); echo "duration $D"
ffmpeg -hide_banner -nostats -i $NAME.mp4 -af ebur128=peak=true -f null - 2>&1 | grep -E "^ +(I|Peak):" | tail -2
mkdir -p /tmp/claude-0/v3_review; for t in $(seq 5 15 $(python3 -c "print(int($D))")); do ffmpeg -v error -y -ss $t -i $NAME.mp4 -frames:v 1 /tmp/claude-0/v3_review/s_$(printf %03d $t).png; done
ffmpeg -v error -y -i $NAME.mp4 -vf "fps=20/$D,scale=480:-1,tile=4x5" -frames:v 1 ${NAME/feedback/sheet}.jpg
