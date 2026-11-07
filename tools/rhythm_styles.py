import os as _os  # panel address comes from the LED_ADDR environment variable
import asyncio, time
from bleak import BleakClient
try:
    from bleak.backends.bluezdbus.version import BlueZFeatures
    BlueZFeatures.checked_bluez_version=True; BlueZFeatures.supported_version=True
except Exception: pass
ADDR=_os.environ["LED_ADDR"]; W="0000fa02-0000-1000-8000-00805f9b34fb"; N="0000fa03-0000-1000-8000-00805f9b34fb"
def rhythm(s,lv): return bytes([0x10,0x00,0x01,0x02,s]+[max(0,min(15,int(v))) for v in lv])
import math
async def main():
    async with BleakClient(ADDR) as c:
        await c.start_notify(N, lambda *_:None)
        for s in range(5):
            print(f"style {s} — animated sweep 3s", flush=True)
            t0=time.monotonic()
            while time.monotonic()-t0<3:
                t=time.monotonic()-t0
                lv=[7+8*math.sin(t*4+i*0.7) for i in range(11)]
                await c.write_gatt_char(W, rhythm(s,lv), response=False); await asyncio.sleep(1/15)
        await c.write_gatt_char(W, rhythm(0,[0]*11), response=False)
asyncio.run(main())
