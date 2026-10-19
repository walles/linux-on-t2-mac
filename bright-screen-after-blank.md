# Bright screen after blank

When GNOME turns the screen off and on again, the screen comes back much
brighter than it was. The brightness slider doesn't move. Moving the slider,
or pressing a Touch Bar brightness key, brings it back to normal.

Upstream:
[gnome-shell #8744](https://gitlab.gnome.org/GNOME/gnome-shell/-/issues/8744),
"screen set to max brightness after screen blank", reported on another
MacBook Pro 2019 (T2) with GNOME 49.1. On 2026-10-19 swick (mutter) answered
that the driver or firmware sets the backlight without notifying through
udev, and that it should be reported against the kernel. Not reported yet.

## Cause

The gmux brightness register is changed while the screen is off, and nothing
tells the kernel.

- The screen backlight is `gmux_backlight`, from `apple_gmux`. i915 and
  amdgpu both skip registering their own.
- In `/sys/class/backlight/gmux_backlight/`, `actual_brightness` reads the
  gmux register, and `brightness` is the value the kernel last wrote.
- Within a second of the screen going off, the register changes to 52428
  (`0xCCCC`, exactly 80% of 65535). `brightness` keeps the old value, and no
  udev event is sent, so mutter can't notice.
- When the screen comes back on, the register is still at 80%, and that's
  what the screen shows.
- Writing the old value back through logind, like mutter does, restores both
  the register and what the screen shows.

It happens the same way with the panel on the Intel GPU (`force_igd=y`)
and on the Radeon, so it isn't caused by t2linux's `force_igd` patch, and
it isn't specific to i915 or amdgpu.

The reset comes from the hardware or firmware, not from the kernel. It
happens about 80 ms after i915 turns off the panel power, at the moment the
panel reports being off. The backlight enable going off and the PWM going to
0 come before it, and change nothing. Nothing is logged at the moment of the
reset, and no ACPI event fires.

`apple_gmux` can't easily fix this. It is only told about system suspend and
resume (`BL_CORE_SUSPENDRESUME` makes the backlight core write the brightness
back after a resume). Nothing tells it when the screen goes off or on.

## Measurements

2026-10-19, kernel 7.2.8-1-t2, GNOME 50.1, automatic brightness off. The
screen was blanked through mutter for 5 s, with
`udevadm monitor --kernel --udev --subsystem-match=backlight` running:

```sh
dc=(org.gnome.Mutter.DisplayConfig /org/gnome/Mutter/DisplayConfig org.gnome.Mutter.DisplayConfig PowerSaveMode)
busctl --user set-property "${dc[@]}" i 3   # screen off
busctl --user set-property "${dc[@]}" i 0   # screen on
```

| When | `brightness` | `actual_brightness` |
|---|---|---|
| Before | 19525 (30%) | 19525 |
| 1 s into the blank, to the end of it | 19525 | 52428 |
| Screen on, for 10 s | 19525 | 52428 |

No udev events. The screen came back very bright. About a minute later:

```sh
busctl call org.freedesktop.login1 /org/freedesktop/login1/session/auto \
  org.freedesktop.login1.Session SetBrightness ssu backlight gmux_backlight 19525
```

`actual_brightness` read 19525 again and the screen went back to normal.

The same test with the panel on the Radeon (`force_igd` commented out,
the panel on amdgpu's `card2-eDP-1`): 18752 before, 52428 from 1 s into the
blank until after the screen came on, `brightness` stayed at 18752, no udev
events, and the screen came back bright. Writing 18752 back restored it.

### Timing

`blank-timing.py` blanks the screen through mutter while reading
`actual_brightness` every 2 ms, and prints the kernel log for the same time.
With `drm.debug=0x106`, back on the Intel GPU (`force_igd=y`), two runs:

| i915 step | Run 1 | Run 2 |
|---|---|---|
| Backlight enable off | 216.349 | 304.883 |
| PWM set to 0 | 216.603 | 305.140 |
| Panel power off | 216.621 | 305.142 |
| **Register reads 52428** | **216.701** | **305.222** |
| Panel reports power off | 216.703 | 305.224 |

The register reads were made between the kernel log lines, so the reset
happened within a few ms before the time given. The kernel log has nothing
from `apple_gmux` or ACPI in that window. The ACPI event counters in
`/sys/firmware/acpi/interrupts/` didn't move in the second run. In an
earlier run the Embedded Controller's GPE (0x6E) fired 127 times, but that
didn't happen again.

Not related to the ACPICA bug in `suspend-notes.md`, where the Thunderbolt
mailbox commands go to the wrong PCI device after D3cold. During a blank
with the reset, the Thunderbolt root ports, bridges, NHIs and USB
controllers didn't change power state: the used ones stayed active in D0,
and the unused bridges suspended in D3hot, with 0 ms active time. So no
Thunderbolt `_PS0` ran.

The screen was also bright once after a resume from suspend (2026-10-16).
That may be the same reset, or the backlight core's write after the resume
getting lost. Not tested.

## Next steps

1. Report it to platform-driver-x86@vger.kernel.org (Hans de Goede, Ilpo
   Järvinen), cc Orlando Chamberlain and Lukas Wunner. It happens on the
   Radeon too, so it isn't a t2linux-only bug. The question for them is
   where a fix should go, since `apple_gmux` isn't told when the panel
   powers on. Maybe the GPU drivers could tell the backlight device that
   the panel came back.
2. Test suspend with the screen on and off, with and without the apple-gmux
   patch from `black-screen-after-resume.md`.
3. Find out why it started with GNOME 49. The reporter is sure it didn't
   happen before. Possibly gnome-settings-daemon ≤ 48 wrote the brightness
   back after the screen came on, and so hid the reset. If so, mutter
   writing its brightness back on screen on would be a real workaround.
   swick's patch on #8744 only reads it again, which would move the slider
   to 80% instead of restoring the old level.
4. Post these numbers on #8744.
