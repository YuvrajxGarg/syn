"""Synthetic shoots for the tests: one "world" of sound, heard by several devices.

Each device hears the same events through its own microphone (different EQ, level,
noise floor and room echo), and records clips that start at known times.
"""
import os
import subprocess
import wave

import numpy as np

RATE = 8000


def world(seconds, seed=0, rate=RATE):
    """Speech-like sound: syllable bursts of band-limited noise with pitch, plus a few claps."""
    rng = np.random.default_rng(seed)
    n = int(seconds * rate)
    out = np.zeros(n, np.float32)
    t = 0.0
    while t < seconds - 0.5:
        dur = rng.uniform(0.08, 0.3)
        i0, i1 = int(t * rate), int(min(seconds, t + dur) * rate)
        m = i1 - i0
        f0 = rng.uniform(90, 260)
        tt = np.arange(m) / rate
        voiced = np.sin(2 * np.pi * f0 * tt) + 0.5 * np.sin(2 * np.pi * 2 * f0 * tt) + 0.3 * np.sin(2 * np.pi * 3 * f0 * tt)
        noise = rng.standard_normal(m)
        env = np.hanning(m) * rng.uniform(0.2, 1.0)
        out[i0:i1] += (0.7 * voiced + 0.3 * noise) * env
        t += dur + (rng.uniform(0.02, 0.15) if rng.random() < 0.8 else rng.uniform(0.3, 1.2))
    for _ in range(int(seconds / 30) + 1):
        i = int(rng.uniform(0, seconds - 0.05) * rate)
        out[i:i + 200] += rng.standard_normal(200) * np.exp(-np.arange(200) / 40.0) * 2.0
    return out / (np.abs(out).max() + 1e-9)


def mic(signal, seed, gain=1.0, noise=0.02, tilt=0.0, echo=0.0, rate=RATE):
    """How one device hears the world."""
    rng = np.random.default_rng(1000 + seed)
    x = signal.copy()
    if tilt > 0:
        # darker, like a camera's built-in mic: short smoothing kernel
        k = int(2 + 10 * min(0.95, tilt))
        ker = np.exp(-np.arange(k) / (k / 3.0))
        x = np.convolve(x, ker / ker.sum(), mode="same").astype(np.float32)
    elif tilt < 0:
        # brighter, like a lav close to the mouth
        x = (np.concatenate([[0.0], np.diff(x)]) * 0.6 + x * 0.4).astype(np.float32)
    if echo:
        d = int(0.023 * rate)
        x = x.copy()
        x[d:] += echo * x[:-d]
    x = x * gain + rng.standard_normal(len(x)).astype(np.float32) * noise
    return np.clip(x, -1, 1).astype(np.float32)


def cut(heard, start, dur, rate=RATE):
    return heard[int(start * rate): int((start + dur) * rate)]


def write_wav(path, x, rate=RATE, channels=1):
    pcm = (np.clip(x, -1, 1) * 32000).astype("<i2")
    if channels > 1:
        pcm = np.repeat(pcm[:, None], channels, axis=1).reshape(-1)
    with wave.open(path, "wb") as w:
        w.setnchannels(channels)
        w.setsampwidth(2)
        w.setframerate(rate)
        w.writeframes(pcm.tobytes())
    return path


def write_video(path, x, ffmpeg, fps=24, rate=RATE, size="160x90"):
    """A tiny test-pattern video with the given sound."""
    wav = path + ".tmp.wav"
    write_wav(wav, x, rate)
    dur = len(x) / float(rate)
    subprocess.check_call([ffmpeg, "-loglevel", "error", "-y", "-f", "lavfi", "-i",
                           "testsrc2=size=%s:rate=%s:duration=%.3f" % (size, fps, dur), "-i", wav,
                           "-c:v", "mpeg4", "-q:v", "20", "-c:a", "aac", "-b:a", "64k", "-shortest", path])
    os.remove(wav)
    return path
