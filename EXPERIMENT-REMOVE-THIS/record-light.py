#!/usr/bin/env python3
"""Record ambient light readings as gsd-power sees them.

Claims the light sensor from iio-sensor-proxy, like gsd-power does, and
writes one CSV line per LightLevel update: seconds since boot (keeps
counting during suspend), wall clock, lux. Changes in sensor availability are
logged as lines with an empty lux and a note.

Usage: record-light.py <out.csv> [seconds]
"""

import sys
import time

import gi

gi.require_version("Gio", "2.0")
gi.require_version("GLibUnix", "2.0")
from gi.repository import Gio, GLib, GLibUnix  # noqa: E402

out_path = sys.argv[1]
duration = float(sys.argv[2]) if len(sys.argv) > 2 else None

out = open(out_path, "w", buffering=1)
out.write("boot_s,wall,lux,note\n")


def write(lux, note=""):
    boot_s = time.clock_gettime(time.CLOCK_BOOTTIME)
    wall = time.strftime("%Y-%m-%dT%H:%M:%S")
    out.write(f"{boot_s:.3f},{wall},{lux},{note}\n")


proxy = Gio.DBusProxy.new_for_bus_sync(
    Gio.BusType.SYSTEM,
    Gio.DBusProxyFlags.NONE,
    None,
    "net.hadess.SensorProxy",
    "/net/hadess/SensorProxy",
    "net.hadess.SensorProxy",
    None,
)


def on_properties_changed(_proxy, changed, _invalidated):
    changed = changed.unpack()
    if "HasAmbientLight" in changed:
        write("", f"HasAmbientLight={changed['HasAmbientLight']}")
    if "LightLevel" in changed:
        write(changed["LightLevel"])


proxy.connect("g-properties-changed", on_properties_changed)
proxy.call_sync("ClaimLight", None, Gio.DBusCallFlags.NONE, -1, None)
unit = proxy.get_cached_property("LightLevelUnit").unpack()
print(f"Claimed light sensor, unit: {unit}", file=sys.stderr)

# The cached value can be stale from before claiming. It's recorded for
# reference, marked so the simulator skips it, and the first real update
# follows shortly.
write(proxy.get_cached_property("LightLevel").unpack(), "cached")

loop = GLib.MainLoop()
if duration:
    GLib.timeout_add(int(duration * 1000), loop.quit)
GLibUnix.signal_add(GLib.PRIORITY_DEFAULT, 2, loop.quit)  # SIGINT
GLibUnix.signal_add(GLib.PRIORITY_DEFAULT, 15, loop.quit)  # SIGTERM
loop.run()

proxy.call_sync("ReleaseLight", None, Gio.DBusCallFlags.NONE, -1, None)
out.close()
