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

## Next

- `rtcwake -m mem -s 30` with `amdgpu-off` disabled, to see if deep works
  apart from the Radeon.
- If it does: patch amdgpu to skip the reset in `suspend_noirq` when
  vgaswitcheroo has powered the card off.

## Side findings

- `fwupd-refresh` probes the powered off Radeon, which gives hundreds of
  `amdgpu: REG_WAIT timeout` errors. It might be what started the fan before
  test 4.
- macOS says the computer was shut down because of a problem after each hard
  power off. Harmless.
