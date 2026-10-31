# Automatic Screen Brightness

Problem: the backlight kept changing on its own, a step up, a step down, even
in steady light. Manual changes (GNOME slider, Touch Bar) only helped for a
while.

Status: turned off. Brightness now only changes when told to. Work on a
better algorithm is in progress, see [Improving it](#improving-it).

## Setup

Takes effect immediately.

```
gsettings set org.gnome.settings-daemon.plugins.power ambient-enabled false
```

Same as Settings → Power → Power Saving → Automatic Screen Brightness. Undo
with `gsettings reset org.gnome.settings-daemon.plugins.power ambient-enabled`.

## Why it was jittery

Chain: ambient light sensor (`/sys/bus/iio/devices/iio:device0`, name `als`)
→ `iio-sensor-proxy` (D-Bus `net.hadess.SensorProxy`, `LightLevel` in lux)
→ `gsd-power` computes a target → GNOME Shell sets `gmux_backlight`.

1. The sensor is coarse. In steady light it alternates between two or three
   values from one reading to the next, for example 15454, 16092, 15454,
   16092. In dimmer light the step is a bigger fraction of the reading:
   2692 / 3330 is about 20% apart.
2. GNOME maps light level linearly to brightness. When you set the brightness
   by hand, the current light level becomes the new reference, and from then
   on brightness follows the light level proportionally. So a 20% jump in the
   reading gives a 20% jump in brightness.
3. The smoothing doesn't smooth sparse readings. `gsd-power` uses an
   exponential moving average where the weight of each new reading depends
   on the time since the previous one (time constant 1.6 s, from
   `GSD_AMBIENT_BANDWIDTH_HZ 0.1`). But during that time the light was at the
   *previous* reading. The sensor only reports changes, so after a few quiet
   seconds a new reading gets almost all of the weight (10 s gap → 86%) and
   the brightness jumps nearly all the way.

## Sensor behaviour

Measured 2026-10-16 and 2026-10-17. Data and scripts are in
[`auto-brightness/`](auto-brightness/).

- The values aren't really lux. Indoors they range from ~10,000 to ~150,000,
  and outside on a not-too-bright afternoon ~1.5 million (real daylight is at
  most ~100,000 lux). GNOME only compares readings to each other, so the
  scale itself doesn't matter.
- `iio-sensor-proxy` reports a new value every 0.8 s, or a multiple of that,
  and only when the value changes. The D-Bus value equals
  `in_illuminance_raw` (scale 1).
- In a dark room it reads 0, with an occasional 337 or 582. `gsd-power`
  ignores readings of 0, so in the dark GNOME's auto-brightness keeps
  whatever level it had from somewhere brighter.
- The screen's own light doesn't affect it: going from 1% to 100% backlight
  changed the reading by ~4%, less than its own step.
- Covering it with a hand drops the reading to ~1,500, and it comes back to
  the previous level within a second of uncovering.
- Unexplained: on 2026-10-16 the level went ~14,000 → ~2,000 → ~45,000 within
  two minutes (20:32–20:34), apparently without the light changing. The
  second jump was across a lid close. It didn't happen during the walk on
  2026-10-17.

## Preferred brightness

On 2026-10-17 I walked between places with different light, about two
minutes each, and at each one set the brightness to what looked right.
Automatic brightness was off. Sensor value is the median over the 20 s
before each setting.

| Place | Sensor | Backlight |
|---|---|---|
| Dark room | 0 (sometimes 337–582) | 1–2% (6% the first time, after a shorter stay) |
| Badly lit room | ~12,000 | 6%, three times (21% the very first time) |
| Well lit room | ~106,000 / ~146,000 | 16%, both times |
| Outside, afternoon | ~1.44 / ~1.53 million | 46% / 36% |

Backlight is `gmux_backlight` as a percentage of 65535. The very first
setting was before I had been anywhere else, so I don't trust it.

That's a power law, not a straight line:
`backlight ≈ 6% × (sensor / 12,000)^0.4`. Each 10× more light means about
2.5× more brightness. It gives 15% at 125,000 (I chose 16%), 41% at
1.48 million (36–46%), and 1.4% at 337 (1.8%).

GNOME's linear mapping can't fit this. Anchored at 6% in the badly lit room it
would choose 60% in the well lit room and 100% outside. Anchored at 40%
outside it would choose 3% in the well lit room.

The power law also damps the jitter: with exponent 0.4, a 10% flap in the
reading becomes a 4% flap in brightness.

Other observations:

- Eyes take minutes to adapt to the dark. After 1.5 minutes in the dark room
  6% looked right, after 3.5 minutes 1–2% did. So dimming should be slower
  than brightening.
- GNOME's brightness keys move in 5% steps: 1%, 6%, 11%, ... The Shell
  slider can set values in between.

## Tuning

There's nothing to tune in GNOME. The filter constants are `#define`s in
`plugins/power/gsd-power-manager.c` with no gsettings keys, so changing them
means rebuilding `gnome-settings-daemon`.

The sensor driver has a reporting threshold that might help, untested:
`in_illuminance_hysteresis_relative` is 15 (%), smaller than the flapping
step in dim light. Raising it above ~25 should stop the flapping, though real
changes would then be reported in bigger steps. It's root-writable sysfs, so
making it stick needs a udev rule.

## Improving it

Upstream, as of 2026-10-17:

- [gnome-settings-daemon #277](https://gitlab.gnome.org/GNOME/gnome-settings-daemon/-/issues/277),
  "Automatic brightness changes it too often", open since 2015. Same symptom.
- [gnome-settings-daemon !374](https://gitlab.gnome.org/GNOME/gnome-settings-daemon/-/merge_requests/374),
  "power: Implement linear auto-brightness". Brightens fast and dims slowly,
  and allows per-device mappings. Stalled since 2024 on where the code should
  live (developers want auto-brightness moved out of gsd), and has conflicts.
  I asked on 2026-10-16 whether I can help.
- [gnome-settings-daemon !340](https://gitlab.gnome.org/GNOME/gnome-settings-daemon/-/merge_requests/340),
  backlight brightness curve, open since 2023.
- [gnome-shell !4347](https://gitlab.gnome.org/GNOME/gnome-shell/-/merge_requests/4347)
  (rewrite with smooth changes, close to landing),
  [!4291](https://gitlab.gnome.org/GNOME/gnome-shell/-/merge_requests/4291)
  (smooth auto-brightness changes) and
  [!4467](https://gitlab.gnome.org/GNOME/gnome-shell/-/merge_requests/4467)
  (brightness jumping towards full, found on an M1 MacBook). These make
  transitions smooth, but the flapping would still come through, only more
  gently. !4347 keeps the slider bias (`target + slider − 0.5`) unchanged,
  checked 2026-10-17. Its smoothing moves 8% of the remaining distance every
  16 ms, a time constant of about 0.2 s, so each step becomes a short fade.
- [gnome-shell #9463](https://gitlab.gnome.org/GNOME/gnome-shell/-/issues/9463),
  the slider jumps to full brightness while being dragged with
  auto-brightness on (M1 MacBook). A different bug in the same code.

Plan:

1. A gsd MR that adds a 10% relative dead zone: only send a new target to
   Shell when it differs from the last one sent by more than 10%. Smallest
   change that removes most of the flapping, see the table below.
2. Maybe: fix the smoothing timing, with a single wakeup only when needed
   instead of polling. On top of the dead zone it gains little.
3. Post the preferred-brightness measurements on !374 or #277 as evidence for
   a power-law mapping, linking the data in this repo (public on GitHub,
   `walles/linux-on-t2-mac`). That's a design question upstream hasn't
   settled.

Simulation, replaying the walk with the brightness set once to 6% at the
start (details and chart in [`auto-brightness/`](auto-brightness/)):

| | Typical miss | Changes while standing still | Lag brighter / darker | Timer wakeups |
|---|---|---|---|---|
| Stock GNOME 50 | ×3.1 | 31 | erratic, −15..+14 s | 0 |
| Fixed timing, stock mapping | ×2.5 | 4 | −2..+33 s | 410 |
| Fixed timing + power law | ×1.06* | 2 | 3–10 s / 12–20 s | 127, 2 while still |
| Stock + 10% dead zone | ×2.8 | 3 | as stock | 0 |

\* Fitted to the same walk, so flattering. In GNOME 50, Shell sets
backlight = gsd's target + slider − 50%, and gsd maps the current light to a
66.7% target whenever the slider moves, so with auto-brightness on the
backlight can't go below ~17% in steady light. Verified 2026-10-17: turning
auto-brightness on with the slider at 6% gave 22.7% (66.7 + 6 − 50), and the
slider all the way left gave 15.5–17.1%. In those seconds a 2% change in the
reading moved the backlight by 10%, since Shell's bias turns small changes in
the target into big relative changes at low backlight. Same in the plain
GNOME session without Ubuntu's extensions: starting at 1% gave 17.5–18.3%,
and the slider all the way left gave 17.2–18.5%. That's a Shell-side
problem, separate from the gsd smoothing, reported as
[gnome-shell #9488](https://gitlab.gnome.org/GNOME/gnome-shell/-/issues/9488).

The dead zone row is plan step 1. It also cuts the updates sent to Shell
from 634 to 32. The gsd MR links to
[`auto-brightness/dead-zone.md`](auto-brightness/dead-zone.md), which
presents this result for upstream readers: the recording, the replay and
the metrics. To reproduce, in `auto-brightness/`:
`python3 simulate.py walk.csv --notes walk-notes.csv` for the first three
rows, `python3 split-variants.py` for the last.

Working notes, scripts and data are in [`auto-brightness/`](auto-brightness/).

Versions when this was written: GNOME 50, gnome-settings-daemon 50.0,
iio-sensor-proxy 3.8, kernel 7.2.8-1-t2.
