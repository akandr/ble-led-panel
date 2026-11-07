import os as _os  # panel address comes from the LED_ADDR environment variable
"""Audio-reactive music visualizer: MacBook mic -> FFT (11 bands) -> panel rhythm mode.
Usage: ./venv/bin/python rhythm_viz.py [--style 0] [--seconds 30] [--mic 1]"""
import asyncio, subprocess, time, sys, argparse
import numpy as np
from bleak import BleakClient
try:
    from bleak.backends.bluezdbus.version import BlueZFeatures
    BlueZFeatures.checked_bluez_version=True; BlueZFeatures.supported_version=True
except Exception: pass
ADDR=_os.environ["LED_ADDR"]
W="0000fa02-0000-1000-8000-00805f9b34fb"; N="0000fa03-0000-1000-8000-00805f9b34fb"
SR=22050; CHUNK=1470  # ~15 fps of audio
BANDS=11
def rhythm(style, levels): return bytes([0x10,0x00,0x01,0x02,style & 0xFF]+[max(0,min(15,int(v))) for v in levels])
def audio(mic):
    return subprocess.Popen(["ffmpeg","-hide_banner","-loglevel","error","-f","avfoundation","-i",f":{mic}",
        "-ar",str(SR),"-ac","1","-f","s16le","-"],stdout=subprocess.PIPE,bufsize=CHUNK*2)
# log-spaced band edges 60Hz..9kHz
edges=np.logspace(np.log10(60),np.log10(9000),BANDS+1)
freqs=np.fft.rfftfreq(CHUNK,1/SR)
bins=[np.where((freqs>=edges[i])&(freqs<edges[i+1]))[0] for i in range(BANDS)]
async def main():
    ap=argparse.ArgumentParser(); ap.add_argument("--style",type=int,default=0); ap.add_argument("--seconds",type=float,default=30); ap.add_argument("--mic",default="1")
    a=ap.parse_args()
    p=audio(a.mic)
    smooth=np.zeros(BANDS); agc=np.ones(BANDS)*1e-6; win=np.hanning(CHUNK)
    async with BleakClient(ADDR) as c:
        await c.start_notify(N, lambda *_:None)
        print(f"visualizing (style {a.style}, mic :{a.mic}) for {a.seconds:.0f}s — play music", flush=True)
        t0=time.monotonic(); frames=0
        while time.monotonic()-t0 < a.seconds:
            raw=p.stdout.read(CHUNK*2)
            if len(raw)<CHUNK*2: break
            x=np.frombuffer(raw,np.int16).astype(float)/32768.0
            mag=np.abs(np.fft.rfft(x*win))
            band=np.array([mag[b].mean() if len(b) else 0 for b in bins])
            band=np.log1p(band*20)
            agc=np.maximum(agc*0.999, band)                 # slow-decay peak per band
            norm=band/ (agc+1e-6)                            # 0..1 auto-gained
            lv=norm*15
            smooth=np.where(lv>smooth, lv, smooth*0.6+lv*0.4)  # fast attack, slow decay
            await c.write_gatt_char(W, rhythm(a.style, smooth), response=False)
            frames+=1
            dt=1/15 - (time.monotonic()-t0-frames/15)
            if dt>0: await asyncio.sleep(dt)
        print(f"sent {frames} frames in {time.monotonic()-t0:.1f}s -> {frames/(time.monotonic()-t0):.1f} fps", flush=True)
    p.terminate()
asyncio.run(main())
