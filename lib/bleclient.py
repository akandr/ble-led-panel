"""Thin BLE transport for iPixel Color panels with a single persistent notify
subscription. Avoids pypixelcolor's stop/start-notify churn, which loses
notifications on BlueZ 5.50 (Raspbian Buster). Reuses pypixelcolor's command
builders (they return SendPlan byte payloads) and device-info parser."""
import asyncio, inspect, logging
from bleak import BleakClient, BleakScanner
from pypixelcolor.lib.internal_commands import build_get_device_info_command, _handle_device_info_response

NOTIFY = "0000fa03-0000-1000-8000-00805f9b34fb"
WRITE = "0000fa02-0000-1000-8000-00805f9b34fb"
log = logging.getLogger("bleclient")

# Bypass bleak's BlueZ>=5.55 gate from our own code (harmless off-Linux).
try:
    from bleak.backends.bluezdbus.version import BlueZFeatures
    BlueZFeatures.checked_bluez_version = True
    BlueZFeatures.supported_version = True
except Exception:
    pass


async def find_panel(timeout=8.0, prefix="LED_BLE"):
    devs = await BleakScanner.discover(timeout=timeout)
    for d in devs:
        if (d.name or "").startswith(prefix):
            return d.address
    return None


class PanelClient:
    def __init__(self, address):
        self.address = address
        self._c = None
        self._ev = asyncio.Event()
        self._last = None
        self.device_info = None

    def _on_notify(self, _, data):
        self._last = bytes(data)
        self._ev.set()

    async def connect(self):
        self._c = BleakClient(self.address)
        await self._c.connect()
        log.info("connected to %s", self.address)
        await self._c.start_notify(NOTIFY, self._on_notify)
        self._ev.clear()
        await self._c.write_gatt_char(WRITE, build_get_device_info_command(), response=True)
        await asyncio.wait_for(self._ev.wait(), timeout=8)
        self.device_info = await _handle_device_info_response(self._c, self._last)
        log.info("device info: %sx%s", self.device_info.width, self.device_info.height)
        return self.device_info

    fast = False   # True: chunks as write-without-response, wait only for the per-window ACK
    wait_ack = True  # False: fire-and-forget windows (experimental; may overrun the firmware)

    async def execute(self, plan):
        for win in plan.windows:
            self._ev.clear()
            data = win.data
            for i in range(0, len(data), plan.chunk_size):
                await self._c.write_gatt_char(WRITE, data[i:i + plan.chunk_size], response=not self.fast)
            if plan.ack_policy.ack_per_window and win.requires_ack and self.wait_ack:
                try:
                    await asyncio.wait_for(self._ev.wait(), timeout=8)
                except asyncio.TimeoutError:
                    log.warning("no ack for window of '%s'", plan.id)

    async def run(self, builder, *args, **kwargs):
        """Call a pypixelcolor command builder, injecting device_info if it accepts it, and execute the plan."""
        if "device_info" in inspect.signature(builder).parameters:
            kwargs.setdefault("device_info", self.device_info)
        await self.execute(builder(*args, **kwargs))

    async def disconnect(self):
        try:
            await self._c.stop_notify(NOTIFY)
        except Exception:
            pass
        try:
            await self._c.disconnect()
        except Exception:
            pass
