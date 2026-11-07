#!/bin/bash
# v3: playwright webm captures (video/cap3) -> 30 fps mp4 clips for remotion: public/v3 (1080p) and public/v3h (half size, 540p feedback cut)
cd /root/hack/kaiku/video; mkdir -p remotion/public/v3 remotion/public/v3h
for n in home chat voice; do
  nice ffmpeg -v error -y -i cap3/$n.webm -r 30 -vf scale=1920:1080 -c:v libx264 -crf 14 -pix_fmt yuv420p -g 30 remotion/public/v3/$n.mp4
  nice ffmpeg -v error -y -i remotion/public/v3/$n.mp4 -vf scale=960:540 -c:v libx264 -crf 16 -pix_fmt yuv420p -g 30 remotion/public/v3h/$n.mp4
done
nice ffmpeg -v error -y -i cap3/decide.webm -r 30 -vf scale=780:1688 -c:v libx264 -crf 14 -pix_fmt yuv420p -g 30 remotion/public/v3/decide.mp4
nice ffmpeg -v error -y -i remotion/public/v3/decide.mp4 -vf scale=390:844 -c:v libx264 -crf 16 -pix_fmt yuv420p -g 30 remotion/public/v3h/decide.mp4
for n in home chat voice decide; do echo $n $(ffprobe -v error -show_entries format=duration -of csv=p=0 remotion/public/v3/$n.mp4); done
for n in chat decide; do ffmpeg -v error -y -i remotion/public/v3/$n.mp4 -vf "fps=1,scale=240:-1,tile=8x3" -frames:v 1 /tmp/claude-0/v3/t_$n.jpg; done
