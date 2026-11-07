import os as _os  # panel address comes from the LED_ADDR environment variable
"""DIY/fun mode (0x0104) + set_pixel (0x0105) throughput, verified by the MacBook camera.
Tests single-pixel rate and whether multiple set_pixel PDUs batched in one GATT write all take effect."""
import asyncio, subprocess, threading, time
import numpy as np
from bleak import BleakClient
try:
    from bleak.backends.bluezdbus.version import BlueZFeatures
    BlueZFeatures.checked_bluez_version=True; BlueZFeatures.supported_version=True
except Exception: pass
ADDR=_os.environ["LED_ADDR"]
W="0000fa02-0000-1000-8000-00805f9b34fb"; N="0000fa03-0000-1000-8000-00805f9b34fb"
CW,CH=160,90; FR=CW*CH*3; samples=[]; stop=False
def funmode(on): return bytes([5,0,4,1,1 if on else 0])
def pixel(x,y,r,g,b): return bytes([10,0,5,1,0,r,g,b,x,y])
def cam():
    p=subprocess.Popen(["ffmpeg","-hide_banner","-loglevel","error","-f","avfoundation","-framerate","30","-video_size","640x480","-i","0",
        "-vf",f"scale={CW}:{CH}","-r","30","-pix_fmt","rgb24","-f","rawvideo","-"],stdout=subprocess.PIPE,bufsize=FR)
    while not stop:
        b=b""
        while len(b)<FR:
            c=p.stdout.read(FR-len(b))
            if not c: return
            b+=c
        a=np.frombuffer(b,np.uint8).reshape(CH,CW,3); samples.append((time.monotonic(),int((a.max(2)>150).sum())))
    p.terminate()
def bright_now():
    return samples[-1][1] if samples else -1
async def main():
    threading.Thread(target=cam,daemon=True).start(); await asyncio.sleep(2)
    async with BleakClient(ADDR) as c:
        await c.start_notify(N, lambda *_:None)
        base=bright_now(); print(f"baseline bright px (camera): {base}")
        # Clear screen via DIY: enable fun mode, paint all black
        await c.write_gatt_char(W, funmode(True), response=True); await asyncio.sleep(0.3)
        print("fun mode ON")
        # 1) single-pixel fill, white, measure rate + camera ramp
        t0=time.monotonic(); n=0
        for y in range(16):
            for x in range(64):
                await c.write_gatt_char(W, pixel(x,y,255,255,255), response=False); n+=1
        dt=time.monotonic()-t0; await asyncio.sleep(0.6)
        print(f"single-pixel fill: {n} px in {dt:.2f}s -> {n/dt:.0f} px/s; camera bright after = {bright_now()} (was {base})")
        # clear by filling black
        for y in range(16):
            for x in range(64): await c.write_gatt_char(W, pixel(x,y,0,0,0), response=False)
        await asyncio.sleep(0.5)
        # 2) batched: concat K pixel-PDUs per GATT write, white, see if all light
        for K in (2,4,8):
            # clear
            for y in range(16):
                for x in range(64): await c.write_gatt_char(W, pixel(x,y,0,0,0), response=False)
            await asyncio.sleep(0.4); pre=bright_now()
            coords=[(x,y) for y in range(16) for x in range(64)]
            t0=time.monotonic(); writes=0
            for i in range(0,len(coords),K):
                buf=b"".join(pixel(x,y,255,255,255) for x,y in coords[i:i+K])
                await c.write_gatt_char(W, buf, response=False); writes+=1
            dt=time.monotonic()-t0; await asyncio.sleep(0.6); post=bright_now()
            full=post>=0.8*post if False else post
            print(f"batch K={K}: {writes} writes ({len(coords)} px) in {dt:.2f}s -> {len(coords)/dt:.0f} px/s; camera bright {pre}->{post}  {'FULL' if post>5*max(1,pre) and post>2000 else 'PARTIAL?'}")
        await c.write_gatt_char(W, funmode(False), response=True)
    global stop; stop=True
asyncio.run(main())
