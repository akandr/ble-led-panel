import os as _os  # panel address comes from the LED_ADDR environment variable
"""Smoothness sweep: constant-speed bar + ball animation at increasing fps; big fps label before each step."""
import asyncio, io, time, sys, math, argparse
sys.path.insert(0, "lib")
from PIL import Image
from bleclient import PanelClient
from pypixelcolor.commands.send_image import send_image_hex
from pypixelcolor.commands.set_brightness import set_brightness
from font import draw_text, F4, text_width
ADDR = _os.environ["LED_ADDR"]
W, H = 64, 16
SPEED = 40.0   # px/s horizontal, constant regardless of fps
def frame(t):
    im = Image.new("RGB", (W, H), (0, 0, 0)); px = im.load()
    span = W - 2; x = int((t * SPEED) % (2 * span)); x = x if x < span else 2 * span - x
    for y in range(H): px[x, y] = (255, 255, 255); px[x + 1, y] = (255, 255, 255)
    ys = H - 4; yy = (t * 24.0) % (2 * ys); yy = yy if yy < ys else 2 * ys - yy; by = int(yy)
    bx = int(32 + 20 * math.sin(t * 1.5))
    for dy in range(4):
        for dx in range(4):
            if (dx - 1.5) ** 2 + (dy - 1.5) ** 2 <= 3.3: px[(bx + dx) % W, by + dy] = (255, 120, 0)
    px[0, 15] = (0, 80, 255); px[63, 15] = (0, 80, 255)
    return im
def png(im, colors=4):
    b = io.BytesIO(); im.quantize(colors=colors, dither=Image.Dither.NONE).save(b, "PNG", optimize=True); return b.getvalue().hex()
def label(fps):
    im = Image.new("RGB", (W, H), (0, 0, 0)); px = im.load()
    s = f"{fps} FPS"; draw_text(px, (W - text_width(s, F4)) // 2, 4, s, (255, 200, 40), F4); return im
async def main():
    ap = argparse.ArgumentParser(); ap.add_argument("--steps", default="5,10,15,20,25,30"); ap.add_argument("--seconds", type=float, default=10)
    ap.add_argument("--ack", action="store_true", help="wait for window ACK (caps ~16 fps)")
    a = ap.parse_args(); steps = [int(x) for x in a.steps.split(",")]
    c = PanelClient(ADDR); await c.connect(); c.fast = True
    await c.run(set_brightness, 70)
    for fps in steps:
        c.wait_ack = True
        await c.run(send_image_hex, png(label(fps), 4), ".png", resize_method="crop"); await asyncio.sleep(1.5)
        c.wait_ack = a.ack
        print(f"=== {fps} fps for {a.seconds:.0f}s ({'ACK' if a.ack else 'fire-and-forget'}) ===", flush=True)
        period = 1.0 / fps; t0 = time.monotonic(); nxt = t0; n = 0; late = 0
        while time.monotonic() - t0 < a.seconds:
            t = time.monotonic() - t0
            await c.run(send_image_hex, png(frame(t)), ".png", resize_method="crop"); n += 1
            nxt += period; d = nxt - time.monotonic()
            if d > 0: await asyncio.sleep(d)
            else: late += 1
        dt = time.monotonic() - t0
        print(f"    sent {n} frames in {dt:.1f}s -> {n/dt:.1f} fps actual; {late} frames late (sender couldn't keep pace)", flush=True)
    c.wait_ack = True; await c.run(send_image_hex, png(label(0), 4), ".png", resize_method="crop"); await c.disconnect(); print("done", flush=True)
asyncio.run(main())
