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

Unknown so far: whether the gmux firmware resets the register when the panel
powers off, or something in the kernel, like i915 or ACPI, writes it.

`apple_gmux` can't easily fix this. It is only told about system suspend and
resume (`BL_CORE_SUSPENDRESUME` makes the backlight core write the brightness
back after a resume). Nothing tells it when the screen goes off or on.

## Measurements

2026-10-19, kernel 7.2.8-1-t2, GNOME 50.1, `force_igd=y`, automatic
brightness off. The screen was blanked through mutter for 5 s, with
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

The screen was also bright once after a resume from suspend (2026-10-16).
That may be the same reset, or the backlight core's write after the resume
getting lost. Not tested.

## Next steps

1. Repeat with the panel on the Radeon, `force_igd` off in
   `/etc/modprobe.d/apple-gmux.conf`. If the reset goes away, it's a
   t2linux bug
   ([linux-t2-patches](https://github.com/t2linux/linux-t2-patches)), since
   `force_igd` only exists in t2linux's patch 2009. If it stays, report it to
   platform-driver-x86@vger.kernel.org (Hans de Goede, Ilpo Järvinen), cc
   Orlando Chamberlain and Lukas Wunner.
2. Time the reset against i915's panel power-off with `drm.debug`, to find
   out who writes the register.
3. Test suspend with the screen on and off, with and without the apple-gmux
   patch from `black-screen-after-resume.md`.
4. Find out why it started with GNOME 49. The reporter is sure it didn't
   happen before. Possibly gnome-settings-daemon ≤ 48 wrote the brightness
   back after the screen came on, and so hid the reset. If so, mutter
   writing its brightness back on screen on would be a real workaround.
   swick's patch on #8744 only reads it again, which would move the slider
   to 80% instead of restoring the old level.
5. Post these numbers on #8744.
