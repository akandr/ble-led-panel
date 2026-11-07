import os as _os  # panel address comes from the LED_ADDR environment variable
"""Measure the panel's real live-update ceiling using the MacBook camera as the instrument.
Sends rhythm-mode frames (16 B, write-without-response) toggling bars full/empty at rate R;
the camera counts how many brightness transitions the panel actually shows."""
import asyncio, subprocess, threading, time, sys
import numpy as np
from bleak import BleakClient

ADDR = _os.environ["LED_ADDR"]
W_UUID = "0000fa02-0000-1000-8000-00805f9b34fb"; N_UUID = "0000fa03-0000-1000-8000-00805f9b34fb"
CW, CH = 160, 90
FRAME = CW * CH * 3
samples = []   # (t, bright_count)
stop = False

def rhythm(level):
    return bytes([0x10, 0x00, 0x01, 0x02, 0x00] + [level] * 11)

def cam_thread():
    p = subprocess.Popen(["ffmpeg", "-hide_banner", "-loglevel", "error", "-f", "avfoundation",
        "-framerate", "30", "-video_size", "640x480", "-i", "0", "-vf", f"scale={CW}:{CH}",
        "-r", "30", "-pix_fmt", "rgb24", "-f", "rawvideo", "-"], stdout=subprocess.PIPE, bufsize=FRAME)
    while not stop:
        buf = b""
        while len(buf) < FRAME:
            c = p.stdout.read(FRAME - len(buf))
            if not c: return
            buf += c
        a = np.frombuffer(buf, np.uint8).reshape(CH, CW, 3)
        bright = int((a.max(axis=2) > 170).sum())
        samples.append((time.monotonic(), bright))
    p.terminate()

def transitions(t0, t1):
    s = [(t, b) for t, b in samples if t0 <= t <= t1]
    if len(s) < 4: return 0, 0, 0
    v = np.array([b for _, b in s], float)
    lo, hi = np.percentile(v, 5), np.percentile(v, 95)
    if hi - lo < 20: return 0, int(lo), int(hi)
    thr = (lo + hi) / 2
    above = v > thr
    return int((above[1:] != above[:-1]).sum()), int(lo), int(hi)

async def main():
    th = threading.Thread(target=cam_thread, daemon=True); th.start()
    await asyncio.sleep(2.0)
    async with BleakClient(ADDR) as c:
        await c.start_notify(N_UUID, lambda *_: None)
        print("connected; sanity check full/empty ...", flush=True)
        await c.write_gatt_char(W_UUID, rhythm(15), response=False); await asyncio.sleep(1.2)
        await c.write_gatt_char(W_UUID, rhythm(0), response=False); await asyncio.sleep(1.2)
        t = time.monotonic()
        tr, lo, hi = transitions(t - 2.6, t)
        print(f"sanity: bright-pixel range {lo}..{hi}, transitions={tr} (expect 1-2)", flush=True)
        if hi - lo < 20:
            print("Panel not visibly toggling: camera doesn't see it or rhythm mode didn't engage.", flush=True)
        results = []
        for R in [2, 4, 6, 8, 10, 12, 15, 20]:
            n = max(8, int(4 * R)); period = 1.0 / R
            await asyncio.sleep(0.6)
            t0 = time.monotonic(); next_t = t0
            for i in range(n):
                await c.write_gatt_char(W_UUID, rhythm(15 if i % 2 == 0 else 0), response=False)
                next_t += period
                d = next_t - time.monotonic()
                if d > 0: await asyncio.sleep(d)
            t1 = time.monotonic()
            await asyncio.sleep(0.4)
            tr, lo, hi = transitions(t0, t1 + 0.3)
            sent_tr = n - 1
            ratio = tr / sent_tr if sent_tr else 0
            print(f"R={R:2d}/s: sent {n} frames ({sent_tr} toggles) in {t1-t0:.2f}s, camera saw {tr} toggles -> {100*ratio:.0f}%  [bright {lo}..{hi}]", flush=True)
            results.append((R, ratio))
        await c.write_gatt_char(W_UUID, rhythm(0), response=False)
    global stop; stop = True
    ok = [R for R, r in results if r >= 0.85]
    print("\nCeiling (>=85% of toggles visible):", max(ok) if ok else "none", "updates/s", flush=True)

asyncio.run(main())
