"""Grab one camera frame, report the bright-region bbox, save full + a suggested crop."""
import subprocess, sys, numpy as np
import os as _os; _os.makedirs("out", exist_ok=True)
from PIL import Image
CW,CH=1280,720; FR=CW*CH*3
p=subprocess.Popen(["ffmpeg","-hide_banner","-loglevel","error","-f","avfoundation","-framerate","30","-video_size","1280x720","-i","0","-frames:v","20","-pix_fmt","rgb24","-f","rawvideo","-"],stdout=subprocess.PIPE)
buf=b""
while len(buf)<FR*20:
    c=p.stdout.read(FR*20-len(buf))
    if not c: break
    buf+=c
f=np.frombuffer(buf[-FR:],np.uint8).reshape(CH,CW,3)
Image.fromarray(f).save("out/frame_full.jpg",quality=85)
g=f.max(2); thr=max(120, np.percentile(g,99.0))
ys,xs=np.where(g>thr)
if len(xs)>50:
    x0,y0,x1,y1=xs.min(),ys.min(),xs.max(),ys.max()
    print(f"bright bbox x[{x0}:{x1}] y[{y0}:{y1}]  size {x1-x0}x{y1-y0}  center ({(x0+x1)//2},{(y0+y1)//2}) of {CW}x{CH}")
    dh=int((y1-y0)*0.6); dw=int((x1-x0)*0.08)
    cx0,cy0,cx1,cy1=max(0,x0-dw),max(0,y0-dh),min(CW,x1+dw),min(CH,y1+dh)
    Image.fromarray(f[cy0:cy1,cx0:cx1]).save("out/frame_crop.jpg",quality=92)
    print("crop saved")
else:
    print("no bright region — panel dark or out of frame")
