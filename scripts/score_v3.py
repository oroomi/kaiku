#!/usr/bin/env python3
"""v3 (no opener, the trailer opens the film; scenes from build/v3/scenes.json). Sound for the Kaiku submission film: Hype Beat bed (Pixabay licence, credited in notes only) from its first note
+ synthesised FX on the cuts. Film = opener (227 frames) + body (see remotion/src/scenes.ts). -> build/audio/audio_raw.wav"""
import sys, subprocess, json, numpy as np
from scipy.io import wavfile
from scipy.signal import butter, lfilter
sys.path.insert(0, '/root/hack/kaiku/video/remotion')
SR = 48000; FPS = 30
OPEN = 0
scenes = json.load(open('/root/hack/kaiku/video/build/v3/scenes.json'))
total = OPEN / FPS + sum(round(s['dur'] * FPS) for s in scenes) / FPS
BED = '/root/hack/knowledge/launch-video/music/hard/6_hype-beat-607162/6_hype-beat-607162.mp3'
OUT = '/root/hack/kaiku/video/build/v3/audio'
import os; os.makedirs(OUT, exist_ok=True)
subprocess.run(['ffmpeg', '-v', 'error', '-y', '-ss', '0.156', '-i', BED, '-t', str(total + 0.5), '-ar', str(SR), '-ac', '2', OUT + '/bed.wav'], check=True)
sr, bed = wavfile.read(OUT + '/bed.wav'); bed = bed.astype(np.float64) / 32768
N = int(total * SR); bed = bed[:N]; t = np.arange(N) / SR
env = np.clip(t / 0.3, 0, 1) * np.clip((total - t) / 3.0, 0, 1)
mix = bed * env[:, None] * 0.8
rng = np.random.default_rng(11)
def add(sig, t0, g=1.0):
    i = int(t0 * SR); n = min(len(sig), N - i)
    if n > 0: mix[i:i + n, :] += (sig[:n] * g)[:, None]
def whoosh(d=0.45, f0=500, f1=5000, peak=0.5):
    n = int(d * SR); x = rng.standard_normal(n); out = np.zeros(n); zi = None
    for b in range(0, n, 512):
        f = f0 * (f1 / f0) ** (b / n); bb, aa = butter(2, [max(60, f / 1.6) / (SR / 2), min(SR / 2 - 100, f * 1.6) / (SR / 2)], btype='band')
        if zi is None: zi = np.zeros(max(len(aa), len(bb)) - 1)
        s, zi = lfilter(bb, aa, x[b:b + 512], zi=zi); out[b:b + 512] = s
    e = np.sin(np.pi * np.linspace(0, 1, n) ** 0.8) ** 2; out *= e; return out / (abs(out).max() + 1e-9) * peak
def tone(f, d, peak=0.4, dec=18):
    n = int(d * SR); tt = np.arange(n) / SR; return np.sin(2 * np.pi * f * tt) * np.exp(-dec * tt) * peak
def thump(): n = int(0.5 * SR); tt = np.arange(n) / SR; return np.sin(2 * np.pi * (90 - 50 * tt) * tt) * np.exp(-7 * tt) * 0.9
at = OPEN / FPS
events = {}
for s in scenes:
    d = round(s['dur'] * FPS) / FPS
    add(whoosh(0.4, 400, 4500, 0.45), max(0, at - 0.12), 1)
    for c in s['caps']: add(tone(1500, 0.05, 0.12, 70), at + c['a'], 1)
    if s.get('tap') is not None:
        add(tone(900, 0.12, 0.35, 30), at + s['tap'], 1)
    if s['id'] == 'chq':
        add(tone(900, 0.12, 0.35, 30), at + 3.3, 1)
    if s['id'] in ('home', 'ch1', 'ch2', 'ch3'):
        pass
    if s['id'] == 'trailer':
        for x in (0.6, 2.1, 3.55, 7.6, 8.9, 16.55): add(whoosh(0.45, 500, 5000, 0.5), at + x - 0.2, 1)
        for x in (10.38, 19.55): add(thump(), at + x, 0.9)  # v3: the logo lands 1.2 s later than in the 20 s template
        for k, x in enumerate((14.4, 14.55, 14.7)): add(tone(880 * 2 ** (k / 6), 0.5, 0.3, 6), at + x, 1)
    if s['id'] == 'end': add(thump(), at + 0.0, 0.6)
    at += d
mix = np.clip(mix, -1.2, 1.2)
wavfile.write(OUT + '/audio_raw.wav', SR, (mix * 32767).clip(-32768, 32767).astype(np.int16))
print('audio', round(total, 2), 's')
