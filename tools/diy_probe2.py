import os as _os  # panel address comes from the LED_ADDR environment variable
"""Calibrated DIY test: establish panel ROI via white/black full frames, then paced set_pixel fill."""
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
ADDR=_os.environ["LED_ADDR"]
W="0000fa02-0000-1000-8000-00805f9b34fb"; N="0000fa03-0000-1000-8000-00805f9b34fb"
CW,CH=160,90; FR=CW*CH*3; frames=[]; stop=False
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
def latest(): 
    return frames[-1].astype(float) if frames else np.zeros((CH,CW,3))
ev=asyncio.Event(); last=[None]
async def notify_wait(c, data, t=6):
    ev.clear(); await c.write_gatt_char(W, data, response=True)
async def send_png(c, im):
    # use with-ACK path via raw: build send_image_hex plan and write windows waiting notify
    from pypixelcolor.commands.send_image import send_image_hex
    from pypixelcolor.lib.device_info import DeviceInfo
    di=DeviceInfo(device_type=131,mcu_version="",wifi_version="",width=64,height=16,has_wifi=False,password_flag=0,led_type=3)
    b=io.BytesIO(); im.save(b,"PNG"); plan=send_image_hex(b.getvalue().hex(),".png",device_info=di,resize_method="crop")
    for win in plan.windows:
        ev.clear()
        for i in range(0,len(win.data),244):
            await c.write_gatt_char(W, win.data[i:i+244], response=True)
        try: await asyncio.wait_for(ev.wait(), timeout=6)
        except asyncio.TimeoutError: pass
async def main():
    global stop
    threading.Thread(target=cam,daemon=True).start(); await asyncio.sleep(2)
    def cb(_,d): last[0]=bytes(d); ev.set()
    async with BleakClient(ADDR) as c:
        await c.start_notify(N, cb)
        await send_png(c, Image.new("RGB",(64,16),(0,0,0))); await asyncio.sleep(0.8); black=latest()
        await send_png(c, Image.new("RGB",(64,16),(255,255,255))); await asyncio.sleep(0.8); white=latest()
        diff=(white-black).max(2); ys,xs=np.where(diff>40)
        if len(xs)<20:
            print("CAMERA cannot see panel clearly (white/black delta too small). Point/zoom the camera at the panel."); 
            global stop; stop=True; return
        y0,y1,x0,x1=ys.min(),ys.max(),xs.min(),xs.max()
        roi=lambda f: f[y0:y1+1,x0:x1+1].max(2).mean()
        wb, bb = roi(white), roi(black)
        print(f"panel ROI in camera: x[{x0}:{x1}] y[{y0}:{y1}] ({x1-x0+1}x{y1-y0+1}px); white={wb:.0f} black={bb:.0f} contrast={wb-bb:.0f}")
        thr=(wb+bb)/2
        # DIY test: fun mode, clear black, then paced white fill, watch ROI climb
        await c.write_gatt_char(W, funmode(True), response=True); await asyncio.sleep(0.4)
        await send_png(c, Image.new("RGB",(64,16),(0,0,0))); await asyncio.sleep(0.5)
        await c.write_gatt_char(W, funmode(True), response=True); await asyncio.sleep(0.3)
        print("fun mode on; paced single-pixel white fill (sleep 8ms each)...")
        t0=time.monotonic(); n=0; lit=0
        for y in range(16):
            for x in range(64):
                await c.write_gatt_char(W, pixel(x,y,255,255,255), response=False); n+=1
                await asyncio.sleep(0.008)
        dt=time.monotonic()-t0; await asyncio.sleep(0.6); after=roi(latest())
        print(f"paced fill: {n} px in {dt:.1f}s -> {n/dt:.0f} px/s; ROI {bb:.0f}->{after:.0f} (white ref {wb:.0f})")
        print("VERDICT:", "set_pixel WORKS (panel lit via DIY)" if after>thr else "set_pixel had NO visible effect (fun mode/opcode not honored, or overrun)")
        await c.write_gatt_char(W, funmode(False), response=True)
        await send_png(c, Image.new("RGB",(64,16),(0,0,0)))
    stop=True
asyncio.run(main())
