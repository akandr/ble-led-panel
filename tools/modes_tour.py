import os as _os  # panel address comes from the LED_ADDR environment variable
"""Tour the untested firmware-native modes, photograph each with the camera."""
import asyncio, subprocess, threading, time
import numpy as np
from bleak import BleakClient
try:
    from bleak.backends.bluezdbus.version import BlueZFeatures
    BlueZFeatures.checked_bluez_version=True; BlueZFeatures.supported_version=True
except Exception: pass
ADDR=_os.environ["LED_ADDR"]; W="0000fa02-0000-1000-8000-00805f9b34fb"; N="0000fa03-0000-1000-8000-00805f9b34fb"
CW,CH=1280,720; FR=CW*CH*3; frames=[]; stop=False; OUT="writeup/images"; ROI=(150,300,1150,600)
import datetime as dt
def set_time():
    now=dt.datetime.now(); return bytes([5,0,1,0x80,now.hour,now.minute,now.second,0][:8]) if False else bytes([0x08,0x00,0x01,0x80,now.hour,now.minute,now.second,0])
def clock(style): return bytes.fromhex(f"0b0006010{style}01011a0b0706")
def flip(on): return bytes([5,0,6,0x80,1 if on else 0])
def scores(a,b): return bytes([8,0,0x0a,0x80,a&0xff,0,b&0xff,0])
def timer(action): return bytes([5,0,9,0x80,action])
def bright(l): return bytes([5,0,4,0x80,l])
def cam():
    p=subprocess.Popen(["ffmpeg","-hide_banner","-loglevel","error","-f","avfoundation","-framerate","30","-video_size","1280x720","-i","0","-pix_fmt","rgb24","-f","rawvideo","-"],stdout=subprocess.PIPE,bufsize=FR)
    while not stop:
        b=b""
        while len(b)<FR:
            c=p.stdout.read(FR-len(b))
            if not c: return
            b+=c
        frames.append(np.frombuffer(b,np.uint8).reshape(CH,CW,3).copy())
    p.terminate()
def shot(name):
    from PIL import Image
    x0,y0,x1,y1=ROI; Image.fromarray(frames[-1][y0:y1,x0:x1]).save(f"{OUT}/{name}.jpg",quality=92); print("shot",name,flush=True)
async def main():
    global stop
    threading.Thread(target=cam,daemon=True).start(); await asyncio.sleep(2)
    async with BleakClient(ADDR) as c:
        await c.start_notify(N, lambda *_:None)
        await c.write_gatt_char(W, bright(70), response=True)
        await c.write_gatt_char(W, set_time(), response=True); await asyncio.sleep(0.3)
        # firmware clock faces
        for st in (0,1,3,5):
            await c.write_gatt_char(W, clock(st), response=True); await asyncio.sleep(1.8); shot(f"fw_clock_{st}")
        # scoreboard
        await c.write_gatt_char(W, scores(3,12), response=True); await asyncio.sleep(1.5); shot("fw_scoreboard")
        # timer / stopwatch
        await c.write_gatt_char(W, timer(1), response=True); await asyncio.sleep(2.0); shot("fw_timer")
        await c.write_gatt_char(W, timer(0), response=True); await asyncio.sleep(0.3)
        # flip test (photograph clock flipped)
        await c.write_gatt_char(W, clock(0), response=True); await asyncio.sleep(0.5)
        await c.write_gatt_char(W, flip(1), response=True); await asyncio.sleep(1.5); shot("fw_flipped")
        await c.write_gatt_char(W, flip(0), response=True)
    stop=True
asyncio.run(main())
