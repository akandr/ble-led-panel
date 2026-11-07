import os as _os  # panel address comes from the LED_ADDR environment variable
"""Full-frame probe: alternate a bright and a dark 64x16 PNG at rate R, fire-and-forget (no ACK wait),
camera counts visible transitions. Finds where the panel stops keeping up / breaks."""
import asyncio, subprocess, threading, time, io, sys
import numpy as np
from PIL import Image
sys.path.insert(0, "lib")
from bleclient import PanelClient
from pypixelcolor.commands.send_image import send_image_hex
ADDR=_os.environ["LED_ADDR"]
CW,CH=160,90; FRAME=CW*CH*3; samples=[]; stop=False
def cam():
    p=subprocess.Popen(["ffmpeg","-hide_banner","-loglevel","error","-f","avfoundation","-framerate","30","-video_size","640x480","-i","0",
        "-vf",f"scale={CW}:{CH}","-r","30","-pix_fmt","rgb24","-f","rawvideo","-"],stdout=subprocess.PIPE,bufsize=FRAME)
    while not stop:
        b=b""
        while len(b)<FRAME:
            c=p.stdout.read(FRAME-len(b))
            if not c: return
            b+=c
        a=np.frombuffer(b,np.uint8).reshape(CH,CW,3); samples.append((time.monotonic(), int((a.max(axis=2)>170).sum())))
    p.terminate()
def transitions(t0,t1):
    s=[b for t,b in samples if t0<=t<=t1]
    if len(s)<4: return 0,0,0
    v=np.array(s,float); lo,hi=np.percentile(v,5),np.percentile(v,95)
    if hi-lo<20: return 0,int(lo),int(hi)
    ab=v>(lo+hi)/2; return int((ab[1:]!=ab[:-1]).sum()),int(lo),int(hi)
def png(bright):
    im=Image.new("RGB",(64,16),(255,255,255) if bright else (0,0,0))
    if bright:
        px=im.load()
        for y in range(16):
            for x in range(64):
                if (x//4+y//4)%2: px[x,y]=(255,200,0)
    b=io.BytesIO(); im.quantize(colors=4).save(b,"PNG",optimize=True); return b.getvalue().hex()
async def main():
    threading.Thread(target=cam,daemon=True).start(); await asyncio.sleep(2)
    B,D=png(True),png(False)
    c=PanelClient(ADDR); await c.connect(); c.fast=True
    from pypixelcolor.commands.set_brightness import set_brightness
    await c.run(set_brightness,70)
    print("sanity (with ACK)...",flush=True)
    for i in range(4):
        await c.run(send_image_hex, B if i%2==0 else D, ".png", resize_method="crop"); await asyncio.sleep(0.5)
    t=time.monotonic(); tr,lo,hi=transitions(t-2.2,t); print(f"sanity: {tr} toggles seen (expect 3), bright {lo}..{hi}",flush=True)
    res=[]
    for mode,label in ((True,"ACK-wait"),(False,"fire-and-forget")):
        c.wait_ack=mode
        for R in ([8,12,16] if mode else [10,15,20,25,30]):
            n=int(4*R); period=1.0/R; await asyncio.sleep(0.6)
            # resync firmware state before each run
            c.wait_ack=True; await c.run(send_image_hex, D, ".png", resize_method="crop"); c.wait_ack=mode; await asyncio.sleep(0.3)
            t0=time.monotonic(); nxt=t0; sent=0
            for i in range(n):
                try: await c.run(send_image_hex, B if i%2==0 else D, ".png", resize_method="crop"); sent+=1
                except Exception as e: print("  send error:",e,flush=True); break
                nxt+=period; d=nxt-time.monotonic()
                if d>0: await asyncio.sleep(d)
            t1=time.monotonic(); await asyncio.sleep(0.5)
            tr,lo,hi=transitions(t0,t1+0.4); exp=max(1,sent-1); pct=100*tr/exp
            print(f"[{label}] target {R:2d} fps: sent {sent} in {t1-t0:.2f}s (actual {sent/(t1-t0):.1f} fps), camera saw {tr}/{exp} toggles -> {pct:.0f}%",flush=True)
            res.append((label,R,sent/(t1-t0),pct))
    c.wait_ack=True; await c.run(send_image_hex, D, ".png", resize_method="crop"); await c.disconnect()
    global stop; stop=True
    print("\nSUMMARY (>=85% visible = keeps up):")
    for l,R,act,pct in res: print(f"  {l:16s} target {R:2d} -> actual {act:4.1f} fps, visible {pct:3.0f}% {'OK' if pct>=85 else 'DROPS'}")
asyncio.run(main())
