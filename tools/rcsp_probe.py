import os as _os  # panel address comes from the LED_ADDR environment variable
"""READ-ONLY probe of the Jieli RCSP service (ae00/ae01/ae02). Enable notifications, observe any
unsolicited frames, and try a benign RCSP 'get target feature / version' query. No writes to flash, no OTA."""
import asyncio
from bleak import BleakClient
try:
    from bleak.backends.bluezdbus.version import BlueZFeatures
    BlueZFeatures.checked_bluez_version=True; BlueZFeatures.supported_version=True
except Exception: pass
ADDR=_os.environ["LED_ADDR"]
AE_W="0000ae01-0000-1000-8000-00805f9b34fb"; AE_N="0000ae02-0000-1000-8000-00805f9b34fb"
got=[]
# JieLi RCSP framing (public, from AC69 SDK docs): sync 0xFE, then opcode etc. We only READ.
# Benign query candidates seen in RCSP: 0x02 = get target info / version.
PROBES = {
    "rcsp_getver_A": bytes.fromhex("fe"),               # bare sync, usually ignored
    "rcsp_getver_B": bytes.fromhex("fe 00 05 02 00 00 00 00".replace(" ","")),
}
async def main():
    async with BleakClient(ADDR) as c:
        def cb(_,d): got.append(bytes(d)); print("AE02 NOTIFY<-", bytes(d).hex(), flush=True)
        await c.start_notify(AE_N, cb)
        print("notify on ae02; listening 4s for anything unsolicited...", flush=True)
        await asyncio.sleep(4)
        for name,p in PROBES.items():
            print(f"-> {name}: {p.hex()}", flush=True)
            try: await c.write_gatt_char(AE_W, p, response=False)
            except Exception as e: print("   write err", e, flush=True)
            await asyncio.sleep(2.5)
        print("total RCSP notifications:", len(got), flush=True)
asyncio.run(main())
