import os as _os  # panel address comes from the LED_ADDR environment variable
"""Record the panel reacting to music. Pre-decode MP3, drive rhythm mode synced to wall clock,
record camera video, play audio to speakers, then mux the music under the video."""
import asyncio, subprocess, time, sys, argparse, os
import os as _os; _os.makedirs("out", exist_ok=True)
import numpy as np
from bleak import BleakClient
try:
    from bleak.backends.bluezdbus.version import BlueZFeatures
    BlueZFeatures.checked_bluez_version=True; BlueZFeatures.supported_version=True
except Exception: pass
ADDR=_os.environ["LED_ADDR"]; W="0000fa02-0000-1000-8000-00805f9b34fb"; N="0000fa03-0000-1000-8000-00805f9b34fb"
SR=22050; BANDS=11; OUT="out"
def rhythm(s,lv): return bytes([0x10,0x00,0x01,0x02,s]+[max(0,min(15,int(v))) for v in lv])
def decode(path):
    raw=subprocess.run(["ffmpeg","-hide_banner","-loglevel","error","-i",path,"-ar",str(SR),"-ac","1","-f","s16le","-"],stdout=subprocess.PIPE).stdout
    return np.frombuffer(raw,np.int16).astype(float)/32768.0
async def main():
    ap=argparse.ArgumentParser(); ap.add_argument("mp3"); ap.add_argument("--offset",type=float,default=45); ap.add_argument("--dur",type=float,default=22); ap.add_argument("--style",type=int,default=0); ap.add_argument("--name",default="panel_music")
    a=ap.parse_args()
    pcm=decode(a.mp3); win=np.hanning(1470); edges=np.logspace(np.log10(55),np.log10(10000),BANDS+1)
    freqs=np.fft.rfftfreq(1470,1/SR); bins=[np.where((freqs>=edges[i])&(freqs<edges[i+1]))[0] for i in range(BANDS)]
    cam_mp4=f"{OUT}/{a.name}_cam.mp4"; final=f"{OUT}/{a.name}.mp4"
    # start camera recording (video only) and audio playback
    rec=subprocess.Popen(["ffmpeg","-hide_banner","-loglevel","error","-y","-f","avfoundation","-framerate","30","-video_size","1280x720","-i","0","-t",str(a.dur),"-pix_fmt","yuv420p","-c:v","libx264","-preset","veryfast",cam_mp4])
    play=subprocess.Popen(["ffplay","-nodisp","-autoexit","-loglevel","quiet","-ss",str(a.offset),"-t",str(a.dur),a.mp3])
    async with BleakClient(ADDR) as c:
        await c.start_notify(N, lambda *_:None)
        smooth=np.zeros(BANDS); agc=np.ones(BANDS)*1e-3; t0=time.monotonic(); frames=0
        print("recording...", flush=True)
        while time.monotonic()-t0 < a.dur:
            pos=time.monotonic()-t0 + a.offset; idx=int(pos*SR)
            seg=pcm[idx:idx+1470]
            if len(seg)<1470: break
            mag=np.abs(np.fft.rfft(seg*win)); band=np.array([mag[b].mean() if len(b) else 0 for b in bins])
            band=np.log1p(band*25); agc=np.maximum(agc*0.998,band); norm=band/(agc+1e-6); lv=norm*15
            smooth=np.where(lv>smooth, lv, smooth*0.55+lv*0.45)
            await c.write_gatt_char(W, rhythm(a.style,smooth), response=False); frames+=1
            d=t0+frames/15-time.monotonic()
            if d>0: await asyncio.sleep(d)
        print(f"{frames} rhythm frames in {time.monotonic()-t0:.1f}s", flush=True)
    rec.wait(); 
    try: play.wait(timeout=2)
    except Exception: play.terminate()
    # mux: camera video + the exact audio segment
    subprocess.run(["ffmpeg","-hide_banner","-loglevel","error","-y","-i",cam_mp4,"-ss",str(a.offset),"-t",str(a.dur),"-i",a.mp3,
        "-c:v","copy","-c:a","aac","-shortest",final])
    print("FINAL:", final, os.path.getsize(final)//1024,"KB", flush=True)
asyncio.run(main())
