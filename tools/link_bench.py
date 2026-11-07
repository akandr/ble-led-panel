import os as _os  # panel address comes from the LED_ADDR environment variable
"""Raw BLE link throughput to the panel: blast a real 16-colour movie frame as fast as the stack accepts,
fire-and-forget (no ACK wait), no pacing. Reports bytes/s and frames/s the sender achieves for several
frame sizes (palettes), then prints a budget table."""
import asyncio, subprocess, io, time, sys
sys.path.insert(0, "lib")
from PIL import Image, ImageEnhance
from bleclient import PanelClient
from pypixelcolor.commands.send_image import send_image_hex
ADDR=_os.environ["LED_ADDR"]; W,H=64,16; F=W*H*3
SRC=sys.argv[1] if len(sys.argv) > 1 else 'out/source.mov'
def grab(t=12.0):
    p=subprocess.Popen(["ffmpeg","-hide_banner","-loglevel","error","-ss",str(t),"-i",SRC,"-frames:v","1","-vf",f"scale={W}:{H}:force_original_aspect_ratio=increase,crop={W}:{H}","-pix_fmt","rgb24","-f","rawvideo","-"],stdout=subprocess.PIPE)
    b=p.stdout.read(F); return ImageEnhance.Color(ImageEnhance.Contrast(Image.frombytes("RGB",(W,H),b)).enhance(1.4)).enhance(1.4)
def png(im,c):
    o=io.BytesIO(); im.quantize(colors=c,dither=Image.Dither.NONE).save(o,"PNG",optimize=True); return o.getvalue()
async def main():
    im=grab(); frames={c:png(im,c) for c in (4,16,32,64)}
    c=PanelClient(ADDR); await c.connect(); c.fast=True
    res=[]
    for colors,data in frames.items():
        hx=data.hex(); c.wait_ack=True; await c.run(send_image_hex,hx,".png",resize_method="crop"); await asyncio.sleep(0.5)
        c.wait_ack=False; n=0; t0=time.monotonic()
        while time.monotonic()-t0<5.0:
            await c.run(send_image_hex,hx,".png",resize_method="crop"); n+=1
        dt=time.monotonic()-t0
        # wire bytes = plan windows (header + png); approximate as png + 16 B header
        wire=(len(data)+16)*n
        print(f"{colors:2d} kolory, PNG {len(data):3d} B: {n} klatek w {dt:.1f}s -> {n/dt:5.1f} fps nadawcy, {wire/dt/1024:5.1f} KB/s na lacze",flush=True)
        res.append((colors,len(data),n/dt,wire/dt))
        c.wait_ack=True; await asyncio.sleep(1.0)
        try: await c.run(send_image_hex,hx,".png",resize_method="crop")   # resync
        except Exception as e: print("  resync:",e,flush=True)
    await c.disconnect()
    link=max(r[3] for r in res)
    print(f"\nSzacowana przepustowosc lacza (max zmierzony): {link/1024:.1f} KB/s")
    print("Budzet fps = lacze / (PNG+16 B), potem sufit panelu ~21 fps dla malych klatek:")
    for colors,size,fps,_ in res: print(f"  {colors:2d} kolory ({size:3d} B): limit lacza {link/(size+16):5.1f} fps, nadawca osiagnal {fps:5.1f} fps")
asyncio.run(main())
