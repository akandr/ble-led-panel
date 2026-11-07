import os as _os  # panel address comes from the LED_ADDR environment variable
"""Record the panel playing a video file: camera->mp4, panel plays via ACK mode, then mux source audio."""
import asyncio, subprocess, io, time, sys, argparse, os
import os as _os; _os.makedirs("out", exist_ok=True)
sys.path.insert(0, "lib")
from PIL import Image, ImageEnhance
from bleclient import PanelClient
from pypixelcolor.commands.send_image import send_image_hex
from pypixelcolor.commands.set_brightness import set_brightness
ADDR=_os.environ["LED_ADDR"]; W,H=64,16; FRAME=W*H*3
S="out"
def dec(path,fps,start):
    return subprocess.Popen(["ffmpeg","-hide_banner","-loglevel","error","-ss",str(start),"-i",path,"-vf",f"fps={fps},scale={W}:{H}:force_original_aspect_ratio=increase,crop={W}:{H}","-pix_fmt","rgb24","-f","rawvideo","-"],stdout=subprocess.PIPE,bufsize=FRAME)
def rf(p):
    b=b""
    while len(b)<FRAME:
        c=p.stdout.read(FRAME-len(b))
        if not c: return None
        b+=c
    return b
async def main():
    ap=argparse.ArgumentParser(); ap.add_argument("file"); ap.add_argument("--fps",type=int,default=12); ap.add_argument("--start",type=float,default=0); ap.add_argument("--dur",type=float,default=20); ap.add_argument("--colors",type=int,default=16); ap.add_argument("--name",default="panel_video")
    a=ap.parse_args()
    cam=f"{S}/{a.name}_cam.mp4"; final=f"{S}/{a.name}.mp4"
    rec=subprocess.Popen(["ffmpeg","-hide_banner","-loglevel","error","-y","-f","avfoundation","-framerate","30","-video_size","1280x720","-i","0","-t",str(a.dur),"-pix_fmt","yuv420p","-c:v","libx264","-preset","veryfast",cam])
    play=subprocess.Popen(["ffplay","-nodisp","-autoexit","-loglevel","quiet","-ss",str(a.start),"-t",str(a.dur),a.file])
    c=PanelClient(ADDR); await c.connect(); c.fast=True; c.wait_ack=True; await c.run(set_brightness,85)
    p=dec(a.file,a.fps,a.start); t0=time.monotonic()
    while time.monotonic()-t0<a.dur:
        b=rf(p)
        if b is None: break
        im=ImageEnhance.Color(ImageEnhance.Contrast(Image.frombytes("RGB",(W,H),b)).enhance(1.5)).enhance(1.5)
        buf=io.BytesIO(); im.quantize(colors=a.colors,dither=Image.Dither.NONE).save(buf,"PNG",optimize=True)
        await c.run(send_image_hex, buf.getvalue().hex(), ".png", resize_method="crop")
    await c.disconnect(); rec.wait()
    try: play.wait(timeout=2)
    except: play.terminate()
    subprocess.run(["ffmpeg","-hide_banner","-loglevel","error","-y","-i",cam,"-ss",str(a.start),"-t",str(a.dur),"-i",a.file,"-c:v","copy","-c:a","aac","-shortest",final])
    print("FINAL:", final, os.path.getsize(final)//1024,"KB")
asyncio.run(main())
