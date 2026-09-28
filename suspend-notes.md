# Suspend notes

Working notes for the "Suspend to RAM on lid close" TODO. Remove this file once
suspend works, with the conclusions in the commit message.

## Goal

Lower power use, for environmental reasons. Awake on battery: about 7.0 W.

## Setup

- `/sys/power/mem_sleep` is `s2idle [deep]`, ACPI supports S3.
- Kernel command line already has `pm_async=off`.
- logind ignores the lid; `lid-blank-screen` locks and turns off the screen.
- `amdgpu-off` powers off the Radeon through vgaswitcheroo, but the amdgpu driver
  stays bound to it.

## Tests

1. `systemctl suspend` (deep), Radeon off: never suspended. amdgpu tried a
   mode1 reset of the powered off Radeon in `suspend_noirq` and failed with
   -22, so the kernel aborted the suspend. The resume after that killed the
   xHCI controllers at 09:00.0 and 7f:00.0 and then hung. It powered itself
   off after about 30s.
2. `systemctl suspend` with s2idle, Radeon off: went dark, never woke. Hard
   power off. The log ends at `PM: suspend entry (s2idle)`.
3. `pm_test=devices` with `rtcwake -m freeze`: passed. All devices suspended
   and resumed, and the keyboard, trackpad, graphics, sound and wifi all worked
   afterwards. The only complaint was `apple_gmux: Timeout waiting for gmux
   switch to complete`.
4. `rtcwake -m freeze -s 30`, a real s2idle sleep: never woke up, and the fan
   kept running. Hard power off. Not even `suspend entry` was saved to the log.
   So waking from s2idle is broken, even with a timer.
5. `rtcwake -m mem -s 30` with `amdgpu-off` disabled, Radeon on: entered S3
   and resumed. After about a minute the keyboard backlight and touch bar came
   back, and the log shows the keyboard, trackpad and wifi back too. But the
   screen stayed black, maybe with the backlight on. Hard power off after a
   while. amdgpu logged lots of `Adding stream ... failed with err 28` and
   `Cannot find any crtc or sizes` during resume.
6. Same as 5, then `MIGD` to vgaswitcheroo 3s after the resume, to switch only
   the mux back to the Intel GPU. The screen was on but still black. The
   keyboard worked, fn switched the touch bar. vgaswitcheroo showed the same
   state before and after. i915 and GNOME logged nothing during or after the
   resume. The `Adding stream ... err 28` messages happen at every boot too,
   so they're unrelated.

7. Same as 6, then a switch to VT3 and back to VT2. Backlight on, no pixels
   at any point. i915 thinks everything works: eDP-1 connected, the plane
   visible at 3072x1920, and it showed new framebuffers for GNOME and for the
   VT3 console. PSR isn't in use (`i915_edp_psr_status`: No such device). So
   i915 sends out frames, but they don't reach the panel.

8. Same as 5, with drm debug logging (`drm.debug=0x106`), then 5s after the
   resume the screen off and on through GNOME (PowerSaveMode 3, then 0). The
   picture came back 7.8s after the resume, from that alone, before `MIGD`.
   The debug log shows why: during the resume i915 got AUX timeouts from the
   panel, `Set power to D0 failed` and `Link Training failed`, and then kept
   drawing to a dead link without saying so at normal log levels. Turning the
   screen on again later trained the link fine.

9. Screen off through GNOME, then `rtcwake -m mem -s 30`, then screen on
   right after the resume. The picture came back immediately, and the link
   trained 0.28s after `PM: suspend exit`.

## Conclusions

- Suspend to RAM works on this machine. The keyboard, trackpad, touch bar and
  wifi come back.
- The black screen: i915 sets up the panel during the resume, before the panel
  can be reached. Guess: the firmware switches the mux to the Radeon in S3,
  and apple_gmux switches it back only after i915 has resumed. PCI devices
  come before the gmux ACPI device in the resume order, and `pm_async=off`
  makes that order strict.
- With the screen off before suspending and on after, like lid close does,
  the screen works without any kernel fix.
- The Radeon has to be on for suspend to work. Awake, that's about 21 W
  instead of about 7 W, much more than suspend could save. So suspend is only
  worth using with the amdgpu fix below.

## Next

- Measure the power use in suspend: `~/suspend-measure.sh`, an hour asleep.
- Kernel fix: patch amdgpu to skip the reset in `suspend_noirq` when
  vgaswitcheroo has powered the card off, so `amdgpu-off` can stay on.
- Optional kernel fix: a device link from i915 to apple_gmux, so gmux resumes
  first. Needed for suspend without turning the screen off first, like from
  the GNOME menu.

## Side findings

- `fwupd-refresh` probes the powered off Radeon, which gives hundreds of
  `amdgpu: REG_WAIT timeout` errors. It might be what started the fan before
  test 4.
- macOS says the computer was shut down because of a problem after each hard
  power off. Harmless.
