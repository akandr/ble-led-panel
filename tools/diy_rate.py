import os as _os  # panel address comes from the LED_ADDR environment variable
"""Find max reliable set_pixel rate and whether batched PDUs work, camera-verified."""
import asyncio, subprocess, threading, time, io
import numpy as np
from bleak import BleakClient
try:
    from bleak.backends.bluezdbus.version import BlueZFeatures
    BlueZFeatures.checked_bluez_version=True; BlueZFeatures.supported_version=True
except Exception: pass
import sys; sys.path.insert(0, "lib")
from PIL import Image
from pypixelcolor.commands.send_image import send_image_hex
from pypixelcolor.lib.device_info import DeviceInfo
ADDR=_os.environ["LED_ADDR"]
W="0000fa02-0000-1000-8000-00805f9b34fb"; N="0000fa03-0000-1000-8000-00805f9b34fb"
CW,CH=160,90; FR=CW*CH*3; frames=[]; stop=False; ev=asyncio.Event()
DI=DeviceInfo(device_type=131,mcu_version="",wifi_version="",width=64,height=16,has_wifi=False,password_flag=0,led_type=3)
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
        frames.append(np.frombuffer(b,np.uint8).reshape(CH,CW,3).copy())
    p.terminate()
async def send_png(c, im):
    b=io.BytesIO(); im.save(b,"PNG"); plan=send_image_hex(b.getvalue().hex(),".png",device_info=DI,resize_method="crop")
    for win in plan.windows:
        ev.clear()
        for i in range(0,len(win.data),244): await c.write_gatt_char(W, win.data[i:i+244], response=True)
        try: await asyncio.wait_for(ev.wait(), timeout=6)
        except asyncio.TimeoutError: pass
async def main():
    global stop
    threading.Thread(target=cam,daemon=True).start(); await asyncio.sleep(2)
    async with BleakClient(ADDR) as c:
        await c.start_notify(N, lambda _,d: ev.set())
        await send_png(c, Image.new("RGB",(64,16),(0,0,0))); await asyncio.sleep(0.7); black=frames[-1].astype(float)
        await send_png(c, Image.new("RGB",(64,16),(255,255,255))); await asyncio.sleep(0.7); white=frames[-1].astype(float)
        diff=(white-black).max(2); ys,xs=np.where(diff>40); y0,y1,x0,x1=ys.min(),ys.max(),xs.min(),xs.max()
        roi=lambda: frames[-1].astype(float)[y0:y1+1,x0:x1+1].max(2).mean()
        wb=white[y0:y1+1,x0:x1+1].max(2).mean(); bb=black[y0:y1+1,x0:x1+1].max(2).mean(); full=bb+0.80*(wb-bb)
        print(f"ROI ok; white={wb:.0f} black={bb:.0f}; 'full' threshold={full:.0f}")
        coords=[(x,y) for y in range(16) for x in range(64)]
        async def trial(label, delay, K):
            await c.write_gatt_char(W, funmode(True), response=True); await asyncio.sleep(0.2)
            await send_png(c, Image.new("RGB",(64,16),(0,0,0))); await asyncio.sleep(0.4)
            await c.write_gatt_char(W, funmode(True), response=True); await asyncio.sleep(0.2)
            t0=time.monotonic()
            for i in range(0,len(coords),K):
                buf=b"".join(pixel(x,y,255,255,255) for x,y in coords[i:i+K])
                await c.write_gatt_char(W, buf, response=False)
                if delay: await asyncio.sleep(delay)
            dt=time.monotonic()-t0; await asyncio.sleep(0.6); r=roi()
            ok = r>=full
            print(f"{label}: K={K} delay={delay*1000:.0f}ms -> {len(coords)/dt:.0f} px/s, ROI={r:.0f} {'FULL' if ok else 'partial/overrun'}")
            return ok
        # pacing sweep (single pixels)
        for d in (0.008,0.004,0.002,0.001,0.0):
            await trial(f"pace", d, 1)
        # batching sweep (small delay to avoid Mac-queue artifact)
        for K in (2,4,8,16):
            await trial(f"batch", 0.004, K)
        await c.write_gatt_char(W, funmode(False), response=True)
        await send_png(c, Image.new("RGB",(64,16),(0,0,0)))
    stop=True
asyncio.run(main())
