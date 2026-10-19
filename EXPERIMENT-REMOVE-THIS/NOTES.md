# Auto-brightness experiment, working notes

Temporary. Findings go in `../auto-brightness.md`. When done, keep the useful
scripts and data in a permanent directory (for example `auto-brightness/`)
and delete the rest.

## Files

Scripts:

- `record-light.py <out.csv> [seconds]`: claims the light sensor from
  `iio-sensor-proxy` like `gsd-power` does and logs every `LightLevel` update.
  Columns: `boot_s` (`CLOCK_BOOTTIME`, keeps counting during suspend), `wall`,
  `lux`, `note`. The first line is the stale cached value from before the
  claim, marked `cached`. Survives a lid close and resume. Logs
  `HasAmbientLight` changes, none seen so far.
- `simulate.py <recording.csv> [--notes walk-notes.csv] [--anchor PCT]
  [--csv out.csv]` and `simulate.py --selftest`: replays a recording through
  stock GNOME 50 (gsd 50.0 port plus Shell 50.1's slider bias), "fixed
  timing" (stock mapping, event-driven smoothing with a dead zone and no
  polling) and "power law" (plus the power-law mapping, floor, log-domain
  smoothing). The user sets the brightness once at the start. Self-tests check
  the stock port against hand-worked values and the proposed smoothing
  against its closed form, steady light and flapping. Run from this
  directory without `-I`, it imports `calibration.py`.
- `export-chart-data.py <out.json>`: runs the walk through all three and
  writes `walk-chart-data.json`. `walk-chart.template.html` + that JSON →
  `walk-chart.html` (replace `__DATA__`), published as a private artifact:
  https://claude.ai/artifact/U6ksj6RXneMDUjW4Pf3q32
- `calibration.py`: pairs each "looks good" note from the walk with the
  backlight level and the median sensor value over the preceding 20 s.
  Prints the table in `../auto-brightness.md`.
- `run-gsd-power.sh`: doesn't work. It tries to replace the system
  `gsd-power` with a local build, but
  `org.gnome.SettingsDaemon.Power.service` refuses manual stop / start. The
  local build then ran beside the system one without getting any light
  readings. `baseline.log` is its useless output.

Data:

- `walk.csv`, `walk-backlight.csv`, `walk-notes.csv`: the walk on
  2026-10-17 15:29–15:49. Sensor, backlight polled every 0.5 s (`boot_s`,
  raw value of 65535), and timestamped notes ("moving", "looks good"). Notes
  contain commas, so split each line on the first two commas only. Note
  times are when the message reached the agent, a few seconds late.
- `backlight-test.csv`, `backlight-test-screen.csv`: 2026-10-16 22:54,
  brightness at 55% → 1% → 100% → 31%, to check whether the screen's light
  affects the sensor. It doesn't.
- `lid-test.csv`: 2026-10-16 20:33, across a 36 s lid close, plus a hand
  covering the sensor at 20:35:31. Also contains the unexplained jump from
  ~2,000 to ~45,000.
- `test.csv`, `sysfs-test.txt`: first 20 s sample, with `in_illuminance_raw`
  polled in parallel to check that D-Bus and sysfs agree. Can be deleted.

## Stock algorithm, gsd 50.0

`iio_proxy_changed()` in `plugins/power/gsd-power-manager.c` runs on every
`iio-sensor-proxy` property change, with no timer:

- Normalization (at start and after every manual brightness change):
  `norm = reading × 1.5`, and the accumulator starts at 66.7%.
- `brightness = clamp(reading × 100 / norm, 0, 100)`.
- `alpha = 1 / (1 + tau / dt)`, with `tau = 1 / (2π × 0.1 Hz) = 1.59 s` and
  `dt` the time since the previous reading.
- `acc = alpha × brightness + (1 − alpha) × acc`, sent to Shell with
  `SetAutoBrightnessTarget` at most every 0.1 s.
- Readings ≤ 0 are ignored.

The bug: `dt` was spent at the previous reading, but the weight goes to the
new one. The ambient code is identical on upstream `main` (checked
2026-10-16), so the patch will rebase easily.

## Planned design

1. Hold each reading until the next one. On a new reading, first advance the
   average over `dt` using the previous reading, exactly:
   `acc = held + (acc − held) × e^(−dt / tau)`.
2. Dead zone: only send a new target when it differs from the last one sent
   by more than D percentage points.
3. No polling. Since the average is analytic between readings, compute when
   it will cross the dead zone and schedule one wakeup for then
   (`g_timeout_add_seconds`, coalesced). In steady light: no timer wakeups
   at all.
4. Probably a longer `tau`, and slower dimming than brightening.
5. Separately, maybe a later MR: power-law mapping
   (`backlight ∝ reading^0.4`) with a floor, and treating 0 as darkness, not
   as missing data.

Simulator results so far, 20 s of bright-room data: the timing fix alone,
with the stock `tau`, doesn't reduce flapping. A `tau` of 10–20 s or a dead
zone of 2–3 pp removes it completely. Reaction time to real changes isn't
measured yet; `tau` 20 s would take ~45 s to get 90% of the way.

## Next steps

- Done 2026-10-17: simulator rewritten and the walk replayed, results in
  `../auto-brightness.md`. Best variant: power law ^0.4, floor 1%, tau 3 s
  up / 10 s down, dead zone 10%, writes once a second while changing.
- Verified 2026-10-17: with auto-brightness on, the slider at minimum gives
  15.5–17.1% backlight, matching Shell's bias model. See
  `../auto-brightness.md`.
- Then patch gsd, build, and find a way to run it in place of the system
  `gsd-power`. Maybe: kill the system process while preventing systemd from
  restarting it.

## Environment

- gsd clone: `~/src/gnome-settings-daemon`, branch `ambient-hold` from tag
  `50.0` (matches the installed 50.0-1ubuntu1). No changes yet. `origin` is
  `git@ssh.gitlab.gnome.org:GNOME/gnome-settings-daemon.git`. No fork yet.
- Build: `meson setup build -Dprefix=/usr`, then
  `ninja -C build plugins/power/gsd-power`. Works. Build dependencies came
  from `sudo apt build-dep gnome-settings-daemon`, after adding `deb-src` to
  the first `Types:` line of `/etc/apt/sources.list.d/ubuntu.sources`.
- GitLab: `glab` from brew, logged in to gitlab.gnome.org with a `read_api`
  token. Read comments with
  `glab api --hostname gitlab.gnome.org 'projects/GNOME%2Fgnome-settings-daemon/merge_requests/374/notes'`.
  Pushing needs an SSH key on gitlab.gnome.org.
- Automatic brightness is off (`ambient-enabled false`), and stays off between
  experiments.

## Unrelated problem found

The screen comes back very bright after a blank. Moved to
`../bright-screen-after-blank.md`.
