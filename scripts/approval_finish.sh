#!/bin/bash
# After approval_render_chunks.sh prints CHUNKS_DONE: audio score, master, critic, 6 review stills.
cd /root/hack/kaiku/video; grep -q CHUNKS_DONE /tmp/claude-0/chunks.out || { echo "render not done"; exit 1; }
python3 ../scripts/score_approval.py && bash ../scripts/approval_master.sh
/root/hack/kits/critic/critic video /root/hack/kaiku/video/kaiku_approval_cut.mp4 --out /root/hack/kaiku/video/critic_approval > critic_approval.log 2>&1
mkdir -p /tmp/claude-0/appr_review; for t in 3 12 30 60 85 105 126; do ffmpeg -v error -y -ss $t -i kaiku_approval_cut.mp4 -frames:v 1 -vf scale=960:540 /tmp/claude-0/appr_review/t$t.png; done
echo FINISHED
