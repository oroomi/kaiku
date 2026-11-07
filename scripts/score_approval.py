#!/usr/bin/env python3
"""Sound for the approval cut: ElevenLabs narration (vo/*.mp3 at timeline.json cues) over the Hype Beat bed (Pixabay licence, credited in notes only),
ducked under the voice, + synthesised FX (slams, whooshes on beat cuts, click on Accept, rise on the score). -> video/appr/audio_raw.wav, then loudnorm -16 LUFS / -1.5 dBTP."""
import json, subprocess, numpy as np
from scipy.io import wavfile
from scipy.signal import butter, lfilter
R = "/root/hack/kaiku/video/appr"; SR = 48000
TL = json.load(open(R + "/timeline.json")); total = TL["total"]; N = int((total + 0.5) * SR)
BED = '/root/hack/knowledge/launch-video/music/hard/6_hype-beat-607162/6_hype-beat-607162.mp3'
subprocess.run(["ffmpeg", "-v", "error", "-y", "-ss", "0.156", "-i", BED, "-t", str(total + 0.5), "-ar", str(SR), "-ac", "2", R + "/bed.wav"], check=True)
_, bed = wavfile.read(R + "/bed.wav"); bed = bed.astype(np.float64) / 32768
if len(bed) < N: bed = np.pad(bed, ((0, N - len(bed)), (0, 0)))  # bed is shorter than the film: loop its tail quietly
bed = bed[:N]
voice = np.zeros(N)
for v in TL["voice"]:
    f = f"{R}/vo/{v['id']}.wav"; subprocess.run(["ffmpeg", "-v", "error", "-y", "-i", f"{R}/vo/{v['id']}.mp3", "-ar", str(SR), "-ac", "1", f], check=True)
    _, x = wavfile.read(f); x = x.astype(np.float64) / 32768; i = int(v["at"] * SR); n = min(len(x), N - i); voice[i:i + n] += x[:n]
# duck: smoothed voice activity
act = np.convolve(np.abs(voice), np.ones(int(0.12 * SR)) / int(0.12 * SR), mode="same") > 0.01
sm = np.convolve(act.astype(float), np.ones(int(0.35 * SR)) / int(0.35 * SR), mode="same")
t = np.arange(N) / SR
duck = 0.55 - 0.33 * np.clip(sm, 0, 1)            # 0.55 alone, 0.22 under voice
opener = t < TL["opener"]; duck = np.where(opener, np.maximum(duck, 0.62), duck)
env = np.clip(t / 0.3, 0, 1) * np.clip((total - t) / 3.5, 0, 1)
mix = bed * (duck * env)[:, None]
rng = np.random.default_rng(5)
def add(sig, t0, g=1.0):
    i = int(t0 * SR); n = min(len(sig), N - i)
    if n > 0: mix[i:i + n, :] += (sig[:n] * g)[:, None]
def whoosh(d=0.4, f0=400, f1=4500, peak=0.4):
    n = int(d * SR); x = rng.standard_normal(n); out = np.zeros(n); zi = None
    for b in range(0, n, 512):
        f = f0 * (f1 / f0) ** (b / n); bb, aa = butter(2, [max(60, f / 1.6) / (SR / 2), min(SR / 2 - 100, f * 1.6) / (SR / 2)], btype="band")
        if zi is None: zi = np.zeros(max(len(aa), len(bb)) - 1)
        s, zi = lfilter(bb, aa, x[b:b + 512], zi=zi); out[b:b + 512] = s
    e = np.sin(np.pi * np.linspace(0, 1, n) ** 0.8) ** 2; out *= e; return out / (abs(out).max() + 1e-9) * peak
def tone(f, d, peak=0.3, dec=18): n = int(d * SR); tt = np.arange(n) / SR; return np.sin(2 * np.pi * f * tt) * np.exp(-dec * tt) * peak
def thump(): n = int(0.5 * SR); tt = np.arange(n) / SR; return np.sin(2 * np.pi * (90 - 50 * tt) * tt) * np.exp(-7 * tt) * 0.9
for f in (0, 67, 124): add(thump(), f / 30, 0.5); add(tone(1800, 0.06, 0.2, 60), f / 30)
beat = {b["id"]: b["start"] for b in TL["beats"]}
for b in TL["beats"]: add(whoosh(0.4), max(0, b["start"] - 0.12), 0.8)
add(tone(1100, 0.07, 0.3, 50), beat["C"] + 2.4); add(tone(1650, 0.1, 0.2, 30), beat["C"] + 2.45)
for k in range(5): add(tone(660 * 2 ** (k / 12) * 1.5, 0.35, 0.18, 7), beat["C"] + 12.55 + 0.18 * k)
add(thump(), beat["H"], 0.5)
mix = np.clip(mix, -1.2, 1.2) * 0.7 + np.stack([voice, voice], 1) * 1.0
wavfile.write(R + "/audio_raw.wav", SR, (np.clip(mix, -1, 1) * 32767).astype(np.int16))
print("audio", round(total, 2), "s")
