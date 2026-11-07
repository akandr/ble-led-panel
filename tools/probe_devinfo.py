import os as _os  # panel address comes from the LED_ADDR environment variable
"""Dump the raw device-info notification and enumerate all GATT services/characteristics."""
import asyncio
from bleak import BleakClient
try:
    from bleak.backends.bluezdbus.version import BlueZFeatures
    BlueZFeatures.checked_bluez_version=True; BlueZFeatures.supported_version=True
except Exception: pass
ADDR=_os.environ["LED_ADDR"]
W="0000fa02-0000-1000-8000-00805f9b34fb"; N="0000fa03-0000-1000-8000-00805f9b34fb"
INFO=bytes.fromhex("080001800f193a00")
got=[]
async def main():
    async with BleakClient(ADDR) as c:
        print("=== GATT table ===")
        for s in c.services:
            print(f"service {s.uuid}")
            for ch in s.characteristics:
                print(f"  char {ch.uuid}  {ch.properties}")
                for dsc in ch.descriptors:
                    print(f"    desc {dsc.uuid} (h={dsc.handle})")
        def cb(_,d): got.append(bytes(d)); print("NOTIFY<-", bytes(d).hex())
        await c.start_notify(N, cb)
        await c.write_gatt_char(W, INFO, response=True)
        await asyncio.sleep(2)
        print("=== device-info bytes decoded ===")
        if got:
            d=got[0]; print("hex:", d.hex(), "len", len(d))
            print("bytes:", " ".join(f"{b:02x}" for b in d))
asyncio.run(main())
