import os as _os  # panel address comes from the LED_ADDR environment variable
"""Camera -> panel using the custom transport; --fast sends chunks without response."""
import asyncio, subprocess, io, time, sys, argparse
sys.path.insert(0, "lib")
from PIL import Image, ImageEnhance
from bleclient import PanelClient
from pypixelcolor.commands.send_image import send_image_hex
from pypixelcolor.commands.set_brightness import set_brightness
W, H = 64, 16; FRAME = W * H * 3
ADDR = _os.environ["LED_ADDR"]
def ffmpeg(fps):
    return subprocess.Popen(["ffmpeg","-hide_banner","-loglevel","error","-f","avfoundation","-framerate","30",
        "-video_size","1280x720","-i","0","-vf",f"scale={W}:{H}:force_original_aspect_ratio=increase,crop={W}:{H},hflip",
        "-r",str(fps),"-pix_fmt","rgb24","-f","rawvideo","-"], stdout=subprocess.PIPE, bufsize=FRAME)
def read_frame(p):
    b=b""
    while len(b)<FRAME:
        c=p.stdout.read(FRAME-len(b))
        if not c: return None
        b+=c
    return b
async def main():
    ap=argparse.ArgumentParser(); ap.add_argument("--fps",type=int,default=20); ap.add_argument("--fast",action="store_true"); ap.add_argument("--seconds",type=float,default=20); ap.add_argument("--colors",type=int,default=0)
    a=ap.parse_args()
    c=PanelClient(ADDR); await c.connect(); c.fast=a.fast
    await c.run(set_brightness, 70)
    p=ffmpeg(a.fps); n=0; sizes=[]; t0=time.monotonic(); print(f"streaming fast={a.fast} ...", flush=True)
    try:
        while time.monotonic()-t0 < a.seconds:
            b=read_frame(p)
            if b is None: break
            im=ImageEnhance.Color(ImageEnhance.Contrast(Image.frombytes("RGB",(W,H),b)).enhance(1.5)).enhance(1.5)
            if a.colors: im=im.quantize(colors=a.colors, dither=Image.Dither.NONE)
            buf=io.BytesIO(); im.save(buf,"PNG",optimize=True)
            sizes.append(len(buf.getvalue()))
            await c.run(send_image_hex, buf.getvalue().hex(), ".png", resize_method="crop")
            n+=1
            if n%20==0: print(f"{n} frames, {n/(time.monotonic()-t0):.1f} fps", flush=True)
    finally:
        dt=time.monotonic()-t0; print(f"RESULT fast={a.fast} colors={a.colors} avg_png={sum(sizes)//max(1,len(sizes))}B: {n} frames in {dt:.1f}s -> {n/dt:.1f} fps", flush=True)
        p.terminate(); await c.disconnect()
asyncio.run(main())
