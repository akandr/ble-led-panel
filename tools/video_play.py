import os as _os  # panel address comes from the LED_ADDR environment variable
"""Play a video file on the 64x16 panel: ffmpeg decode -> 64x16 -> 16-colour PNG -> BLE fire-and-forget,
paced by wall clock at --fps (cap 21). Audio plays on the Mac via ffplay in parallel."""
import asyncio, subprocess, io, time, sys, argparse
sys.path.insert(0, "lib")
from PIL import Image, ImageEnhance
from bleclient import PanelClient
from pypixelcolor.commands.send_image import send_image_hex
from pypixelcolor.commands.set_brightness import set_brightness
ADDR = _os.environ["LED_ADDR"]
W, H = 64, 16; FRAME = W * H * 3
def decoder(path, fps, start):
    return subprocess.Popen(["ffmpeg", "-hide_banner", "-loglevel", "error", "-ss", str(start), "-i", path,
        "-vf", f"fps={fps},scale={W}:{H}:force_original_aspect_ratio=increase,crop={W}:{H}",
        "-pix_fmt", "rgb24", "-f", "rawvideo", "-"], stdout=subprocess.PIPE, bufsize=FRAME)
def read_frame(p):
    b = b""
    while len(b) < FRAME:
        c = p.stdout.read(FRAME - len(b))
        if not c: return None
        b += c
    return b
async def main():
    ap = argparse.ArgumentParser(); ap.add_argument("file"); ap.add_argument("--fps", type=int, default=12)  # ACK mode self-paces ~12 fps for real video; keep decode rate equal so audio stays in sync
    ap.add_argument("--start", type=float, default=0); ap.add_argument("--colors", type=int, default=16)
    ap.add_argument("--contrast", type=float, default=1.4); ap.add_argument("--sat", type=float, default=1.4)
    ap.add_argument("--noaudio", action="store_true"); ap.add_argument("--ack", action="store_true")
    a = ap.parse_args(); fps = min(a.fps, 21)
    c = PanelClient(ADDR); await c.connect(); c.fast = True; await c.run(set_brightness, 80)
    dec = decoder(a.file, fps, a.start)
    first = read_frame(dec)
    if first is None: print("no frames"); return
    audio = None if a.noaudio else subprocess.Popen(["ffplay", "-nodisp", "-autoexit", "-loglevel", "quiet", "-ss", str(a.start), a.file])
    c.wait_ack = a.ack
    period = 1.0 / fps; t0 = time.monotonic(); n = 0; late = 0; buf = first
    print(f"playing {a.file} at {fps} fps ({'ACK' if a.ack else 'fire-and-forget'}), audio={'off' if a.noaudio else 'on'}", flush=True)
    try:
        while buf is not None:
            im = Image.frombytes("RGB", (W, H), buf)
            im = ImageEnhance.Color(ImageEnhance.Contrast(im).enhance(a.contrast)).enhance(a.sat)
            png = io.BytesIO(); im.quantize(colors=a.colors, dither=Image.Dither.NONE).save(png, "PNG", optimize=True)
            await c.run(send_image_hex, png.getvalue().hex(), ".png", resize_method="crop"); n += 1
            target = t0 + n * period; d = target - time.monotonic()
            if d > 0: await asyncio.sleep(d)
            elif d < -period: late += 1
            if n % (fps * 10) == 0: print(f"  {n/fps:.0f}s: {n/(time.monotonic()-t0):.1f} fps, late {late}", flush=True)
            buf = read_frame(dec)
    finally:
        dt = time.monotonic() - t0; print(f"RESULT: {n} frames in {dt:.1f}s -> {n/dt:.1f} fps, late {late}", flush=True)
        dec.terminate()
        if audio: audio.terminate()
        c.wait_ack = True
        try: await c.disconnect()
        except Exception: pass
asyncio.run(main())
