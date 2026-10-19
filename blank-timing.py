#!/usr/bin/python3
"""Blank the screen through mutter, polling the gmux brightness register.

Shows who resets the brightness while the screen is off, see
bright-screen-after-blank.md. Turn on drm debug messages first:

  echo 0x106 | sudo tee /sys/module/drm/parameters/debug

Prints register changes with CLOCK_MONOTONIC timestamps, which match the
kernel log's timestamps, then the kernel log for the same window. Restores
the brightness through logind at the end.
"""
import subprocess
import time

BL = "/sys/class/backlight/gmux_backlight"
DC = ["org.gnome.Mutter.DisplayConfig", "/org/gnome/Mutter/DisplayConfig",
      "org.gnome.Mutter.DisplayConfig", "PowerSaveMode"]


def now():
    return time.clock_gettime(time.CLOCK_MONOTONIC)


def actual():
    with open(f"{BL}/actual_brightness") as f:
        return int(f.read())


def power_save(mode):
    print(f"[{now():12.6f}] PowerSaveMode {mode}")
    # Don't wait, so polling continues while mutter turns the screen off
    subprocess.Popen(["busctl", "--user", "set-property", *DC, "i", str(mode)])


def poll(seconds, last):
    end = now() + seconds
    while now() < end:
        value = actual()
        if value != last:
            print(f"[{now():12.6f}] actual_brightness {last} -> {value}")
            last = value
        time.sleep(0.002)
    return last


with open(f"{BL}/brightness") as f:
    saved = int(f.read())
start = now()
last = actual()
print(f"[{start:12.6f}] brightness={saved} actual_brightness={last}")

last = poll(1, last)
power_save(3)
last = poll(5, last)
power_save(0)
last = poll(3, last)

subprocess.run(["busctl", "call", "org.freedesktop.login1",
                "/org/freedesktop/login1/session/auto",
                "org.freedesktop.login1.Session", "SetBrightness", "ssu",
                "backlight", "gmux_backlight", str(saved)], check=True)
print(f"[{now():12.6f}] restored {saved}, actual_brightness={actual()}")
end = now()

time.sleep(1)  # Let journald catch up
log = subprocess.run(["journalctl", "-k", "-b", "-o", "short-monotonic",
                      "--no-pager"], capture_output=True, text=True).stdout
print("--- kernel log")
for line in log.splitlines():
    try:
        t = float(line[1:line.index("]")])
    except ValueError:
        continue
    if start - 0.5 <= t <= end + 0.5:
        print(line)
