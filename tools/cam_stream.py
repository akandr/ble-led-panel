import os as _os  # panel address comes from the LED_ADDR environment variable
"""Live MacBook camera -> 64x16 LED panel over BLE.
Usage: ./venv/bin/python cam_stream.py [--fps 10] [--dev 0] [--dry N] [--contrast 1.4]
--dry N: capture+encode N frames without BLE (measures capture pipeline fps).
"""
import asyncio, subprocess, io, time, sys, argparse
import os as _os; _os.makedirs("out", exist_ok=True)
from PIL import Image, ImageEnhance

W, H = 64, 16
FRAME = W * H * 3

def ffmpeg(dev, fps):
    return subprocess.Popen(
        ["ffmpeg", "-hide_banner", "-loglevel", "error",
         "-f", "avfoundation", "-framerate", "30", "-video_size", "1280x720", "-i", dev,
         "-vf", f"scale={W}:{H}:force_original_aspect_ratio=increase,crop={W}:{H},hflip",
         "-r", str(fps), "-pix_fmt", "rgb24", "-f", "rawvideo", "-"],
        stdout=subprocess.PIPE, bufsize=FRAME)

def read_frame(pipe):
    buf = b""
    while len(buf) < FRAME:
        chunk = pipe.stdout.read(FRAME - len(buf))
        if not chunk: return None
        buf += chunk
    return buf

def enhance(im, contrast, sat):
    if contrast != 1.0: im = ImageEnhance.Contrast(im).enhance(contrast)
    if sat != 1.0: im = ImageEnhance.Color(im).enhance(sat)
    return im

async def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--fps", type=int, default=10)
    ap.add_argument("--dev", default="0")
    ap.add_argument("--dry", type=int, default=0)
    ap.add_argument("--contrast", type=float, default=1.5)
    ap.add_argument("--sat", type=float, default=1.5)
    ap.add_argument("--addr", default=None)
    a = ap.parse_args()

    p = ffmpeg(a.dev, a.fps)
    if a.dry:
        t0 = time.monotonic()
        for i in range(a.dry):
            b = read_frame(p)
            if b is None: print("camera ended"); break
            im = enhance(Image.frombytes("RGB", (W, H), b), a.contrast, a.sat)
            io.BytesIO(); im.save(io.BytesIO(), "PNG")
        dt = time.monotonic() - t0
        print(f"DRY: {a.dry} frames in {dt:.2f}s -> {a.dry/dt:.1f} fps (capture+encode only)")
        im.save("out/cam_frame.png")
        p.terminate(); return

    from pypixelcolor import AsyncClient
    addr = a.addr
    if not addr:
        devs = await AsyncClient.scan(8.0)
        f = [d for d in devs if (d.name or "").startswith("LED_BLE")]
        addr = f[0].address if f else _os.environ["LED_ADDR"]
    print("connecting to", addr)
    c = AsyncClient(addr); await c.connect()
    await c.set_brightness(70)
    print("streaming... Ctrl-C to stop")
    n = 0; t0 = time.monotonic()
    try:
        while True:
            b = read_frame(p)
            if b is None: break
            im = enhance(Image.frombytes("RGB", (W, H), b), a.contrast, a.sat)
            buf = io.BytesIO(); im.save(buf, "PNG")
            await c.send_image_hex(buf.getvalue().hex(), ".png", resize_method="crop")
            n += 1
            if n % 10 == 0:
                dt = time.monotonic() - t0
                print(f"{n} frames, {n/dt:.1f} fps")
    except (KeyboardInterrupt, asyncio.CancelledError):
        pass
    finally:
        p.terminate()
        try: await c.disconnect()
        except Exception: pass
        print("stopped")

if __name__ == "__main__":
    asyncio.run(main())
