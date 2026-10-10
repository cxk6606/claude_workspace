"""Synthesize a 30s anime-style soundtrack (pad + piano-like arpeggio + bass + beat + sparkles)."""
import numpy as np
import wave
import sys

SR = 44100
DUR = 30.0
N = int(SR * DUR)
rng = np.random.default_rng(7)
BPM = 96
BEAT = 60 / BPM


def midi(n):
    return 440.0 * 2 ** ((n - 69) / 12)


def env_adsr(n, a, d, s, r):
    t = np.arange(n) / SR
    e = np.ones(n)
    a_n, d_n, r_n = int(a * SR), int(d * SR), int(r * SR)
    e[:a_n] = np.linspace(0, 1, max(a_n, 1))
    e[a_n:a_n + d_n] = np.linspace(1, s, max(d_n, 1))[: max(0, min(d_n, n - a_n))]
    e[a_n + d_n:] = s
    if r_n:
        e[-r_n:] *= np.linspace(1, 0, r_n)
    return e


def add(buf, start, sig, pan=0.5):
    i = int(start * SR)
    if i >= buf.shape[1]:
        return
    sig = sig[: buf.shape[1] - i]
    buf[0, i:i + len(sig)] += sig * (1 - pan)
    buf[1, i:i + len(sig)] += sig * pan


def pluck(freq, dur, vel=1.0):
    n = int(dur * SR)
    t = np.arange(n) / SR
    s = (np.sin(2 * np.pi * freq * t) * 1.0
         + 0.45 * np.sin(2 * np.pi * 2 * freq * t) * np.exp(-t * 6)
         + 0.2 * np.sin(2 * np.pi * 3 * freq * t) * np.exp(-t * 9)
         + 0.08 * np.sin(2 * np.pi * 4.01 * freq * t) * np.exp(-t * 14))
    e = np.exp(-t * 3.2) * np.minimum(t * 400, 1)
    return s * e * vel


def pad(freq, dur):
    n = int(dur * SR)
    t = np.arange(n) / SR
    s = 0
    for det in (-0.004, 0.0, 0.004):
        f = freq * (1 + det)
        # soft saw-ish via few harmonics
        for h, amp in ((1, 1), (2, .35), (3, .15), (4, .06)):
            s = s + amp * np.sin(2 * np.pi * f * h * t + rng.uniform(0, 6.28))
    e = np.minimum(t / 0.9, 1) * np.minimum((dur - t) / 0.9, 1)
    return s * e / 3


def bass(freq, dur):
    n = int(dur * SR)
    t = np.arange(n) / SR
    s = np.sin(2 * np.pi * freq * t) + 0.3 * np.sin(2 * np.pi * 2 * freq * t)
    e = np.minimum(t * 120, 1) * np.exp(-t * 1.6)
    return s * e


def kick():
    n = int(0.35 * SR)
    t = np.arange(n) / SR
    f = 50 + 110 * np.exp(-t * 35)
    ph = 2 * np.pi * np.cumsum(f) / SR
    return np.sin(ph) * np.exp(-t * 11)


def hat(open_=False):
    n = int((0.25 if open_ else 0.06) * SR)
    t = np.arange(n) / SR
    x = rng.standard_normal(n)
    x = np.diff(x, prepend=0)  # crude highpass
    return x * np.exp(-t * (18 if open_ else 90)) * 0.5


def snare():
    n = int(0.22 * SR)
    t = np.arange(n) / SR
    x = np.diff(rng.standard_normal(n), prepend=0) * np.exp(-t * 22)
    return x * 0.6 + np.sin(2 * np.pi * 190 * t) * np.exp(-t * 28) * 0.4


def sparkle(freq0):
    n = int(1.6 * SR)
    t = np.arange(n) / SR
    s = 0
    for k, m in enumerate((1, 1.5, 2, 3, 4)):
        s = s + np.sin(2 * np.pi * freq0 * m * t * (1 + 0.002 * k)) * np.exp(-t * (2.5 + k)) / (k + 1)
    return s * np.minimum(t * 200, 1)


def whoosh(dur=1.2):
    n = int(dur * SR)
    t = np.arange(n) / SR
    x = rng.standard_normal(n)
    # sweeping band via moving-average difference
    k = 40
    lp = np.convolve(x, np.ones(k) / k, mode="same")
    sweep = np.sin(np.pi * t / dur) ** 2
    return (x - lp) * sweep * 0.12


# Chord progression: Am - F - C - G, each 4 beats... 2 bars (8 beats) per chord would be too slow:
# 1 chord per 2 bars of 4/4 at 96 BPM = 10s -> use 1 chord per bar (2.5s): 12 bars in 30s
progression = [
    ("Am", 45, [57, 60, 64]), ("F", 41, [53, 57, 60]),
    ("C", 48, [55, 60, 64]), ("G", 43, [55, 59, 62]),
]
bar = BEAT * 4
n_bars = int(np.ceil(DUR / bar))

L = np.zeros((2, N))
music = np.zeros((2, N))
drums = np.zeros((2, N))
fx = np.zeros((2, N))

for b in range(n_bars):
    name, root, tri = progression[b % 4]
    t0 = b * bar
    sec = t0
    # intensity curve: gentle intro, build, climax
    inten = 0.0 if sec < 5 else (0.5 if sec < 12 else (0.8 if sec < 22 else 1.0))
    # pad
    for nn in tri + [tri[0] + 12]:
        add(music, t0, pad(midi(nn), bar + 0.6) * 0.05, pan=0.35 + 0.3 * rng.random())
    # bass (from bar 2)
    if sec >= 5:
        add(music, t0, bass(midi(root), bar) * 0.22)
        if inten >= 0.8:
            add(music, t0 + BEAT * 2.5, bass(midi(root), BEAT * 1.4) * 0.15)
    # arpeggio: 8th notes, pattern up/down; octave lift in climax
    pat = [0, 1, 2, 3, 2, 1, 2, 1] if inten < 0.8 else [0, 1, 2, 3, 2, 3, 1, 2]
    notes = tri + [tri[0] + 12]
    for i, p in enumerate(pat):
        nn = notes[p] + (12 if sec >= 12 else 0)
        add(music, t0 + i * BEAT / 2, pluck(midi(nn), 1.4, 0.16 + 0.07 * inten),
            pan=0.3 + 0.4 * ((i % 4) / 3))
    # lead melody (from 12s), sparse long notes over chord
    if sec >= 12:
        mel = {"Am": [76, 72, 76, 79], "F": [77, 76, 72, 69],
               "C": [79, 76, 72, 76], "G": [74, 79, 78, 74]}[name]
        rhythm = [0, 1.5, 2.5, 3]
        for r_, nn in zip(rhythm, mel):
            add(music, t0 + r_ * BEAT, pluck(midi(nn), 1.8, 0.28) * 1.0, pan=0.55)
    # drums
    if sec >= 5:
        for beat in range(4):
            tb = t0 + beat * BEAT
            if sec >= 12 and beat in (0, 2) or (sec < 12 and beat == 0):
                add(drums, tb, kick() * 0.5 * (0.7 + 0.3 * inten), pan=0.5)
            if sec >= 12 and beat in (1, 3):
                add(drums, tb, snare() * 0.25, pan=0.5)
            if sec >= 12:
                add(drums, tb, hat() * 0.12, pan=0.6)
                add(drums, tb + BEAT / 2, hat(beat == 3) * 0.14, pan=0.4)

# shooting-star sparkles & whooshes (match video: 3.0, 5.2, 7.0), sunrise swell at ~19s
for ts, f in ((3.0, 1568), (5.2, 1760), (7.0, 2093)):
    add(fx, ts, whoosh(), pan=0.5)
    add(fx, ts + 0.5, sparkle(f) * 0.12, pan=0.5)
# riser into sunrise
rn = int(4 * SR)
tt = np.arange(rn) / SR
riser = np.diff(rng.standard_normal(rn), prepend=0) * (tt / 4) ** 3 * 0.25
add(fx, 16.0, riser, 0.5)
add(fx, 20.0, sparkle(1046) * 0.25, 0.5)
add(fx, 20.0, kick() * 0.9, 0.5)
# soft wind bed
wn = rng.standard_normal(N)
k = 800
wind = np.convolve(wn, np.ones(k) / k, mode="same") * 6
wind *= (0.5 + 0.5 * np.sin(2 * np.pi * np.arange(N) / SR / 6.5)) * 0.05
for c in range(2):
    fx[c] += np.roll(wind, c * 3000)

# reverb on music + fx
def reverb(x, wet=0.25, length=1.8):
    n = int(length * SR)
    t = np.arange(n) / SR
    ir = rng.standard_normal((2, n)) * np.exp(-t * 3.0)
    ir[:, :int(0.02 * SR)] *= np.linspace(0, 1, int(0.02 * SR))
    out = np.zeros_like(x)
    m = N + n
    for c in range(2):
        X = np.fft.rfft(x[c], m)
        H = np.fft.rfft(ir[c], m)
        y = np.fft.irfft(X * H, m)[:N]
        out[c] = y
    return x + wet * out / np.max(np.abs(out) + 1e-9) * np.max(np.abs(x))

mix = reverb(music, 0.55) + reverb(fx, 0.4) + drums * 0.9

# master: fade in/out, normalize
t = np.arange(N) / SR
fade = np.minimum(t / 1.5, 1) * np.minimum((DUR - t) / 2.5, 1)
mix = mix * fade
mix = np.tanh(mix * 1.4)
mix = mix / np.max(np.abs(mix)) * 0.89

pcm = (mix.T * 32767).astype(np.int16)
out = sys.argv[1] if len(sys.argv) > 1 else "audio.wav"
with wave.open(out, "wb") as w:
    w.setnchannels(2)
    w.setsampwidth(2)
    w.setframerate(SR)
    w.writeframes(pcm.tobytes())
print("wrote", out)
