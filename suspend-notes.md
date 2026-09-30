# Suspend notes

Working notes for the suspend TODOs: suspend with the Radeon off, and waking
up quickly. Remove this file once both work, with the conclusions in the
commit message.

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
10. Lid close with `lid-blank-screen` suspending, Radeon on: suspended, and
    opening the lid woke it up. logind and UPower saw the lid open, and the
    screen came back. But waking took about 23s: the lid opened around
    19:40:00, and the user space was back at 19:40:23. Tests 5 and 6 were
    the same: `rtcwake -s 30` came back after 56s both times.
11. All CPUs but CPU 0 offline by hand, then `rtcwake -m mem -s 30`, then the
    CPUs back online. The touch bar and keyboard backlight came back after 55s
    by hand timing, and the kernel says 55.4s from `suspend entry` to
    `suspend exit`. So the delay is the same, and bringing the CPUs back up
    isn't it: that happened only after `suspend exit` here. The screen
    stayed black, since the screen wasn't turned off first. The kernel's
    timestamps put the gap, 27.7s, between `Filesystems sync` and `Freezing
    user space processes` this time, since there was no early CPU offlining.
12. `pm_test=core` with the screen off first: writes `mem` to
    `/sys/power/state`, runs everything but the real sleep and the firmware
    wake, and waits 5s. It took 29.9s by the wall clock, so about 25s extra
    without the firmware being involved. The screen came back, but wifi
    didn't: `brcmfmac: Unable to change power state from D3cold to D0`, and
    probing it again failed. Maybe because there was no real S3 to power it
    back up. The reboot hung after `Rebooting.`, so it needed a hard power
    off.
13. `pm_test=platform`, same as 12: 30.9s by the wall clock, so the delay is
    there too. Wifi died the same way, and the reboot hung the same way.
14. Lid close with `/sys/power/pm_print_times` set to 1. Wifi survived. The
    device resume callbacks took 21.5s in all, and the suspend ones 2.2s.
    The slow resume callbacks, all `pci_pm_resume_noirq` except amdgpu's:

    | Device | Resume |
    |---|---|
    | 06:00.0, Thunderbolt 3 bridge, upstream port | 6.3s |
    | 7c:00.0, the other Thunderbolt 3 bridge | 6.3s |
    | 08:00.0, Thunderbolt 3 NHI | 2.9s |
    | 7e:00.0, the other Thunderbolt 3 NHI | 2.9s |
    | amdgpu (`pci_pm_resume`) | 1.2s |
    | 00:1c.0, the wifi's root port | 1.0s |

    That's 20.6s, run one at a time because of `pm_async=off`. 00:1c.0
    also took 1.0s to suspend. No messages explain the waits.
15. Lid close with the `function_graph` tracer on, limited by
    `set_graph_function` to `pci_pm_suspend_noirq` and `pci_pm_resume_noirq`,
    and `tracing_thresh` at 100ms: never woke up, hard power off. The log
    ends at `PM: suspend entry`. `set_graph_function` only limits what gets
    recorded, all kernel functions still get the tracing hook, maybe also
    in code that can't take it during suspend.
16. Read the ACPI tables (`acpica-tools`, tables from
    `/sys/firmware/acpi/tables`). The Thunderbolt code is in SSDT12, for
    `\_SB.PCI0.PEG1` (00:01.1) and `\_SB.PCI0.PEG2` (00:01.2). Linux says
    yes to `_OSI("Darwin")` on Apple hardware, so it gets the macOS code
    paths (`OSDW ()`):
    - `UPSB._PS0` (the bridges, 06:00.0 and 7c:00.0, 6.3s each) and
      `NHI0._PS0` (2.9s each) both run `PCED`. It retrains the PCIe link to
      the controller and waits for it, in loops with 1s timeouts and sleeps
      of 120ms and 250ms. If the link isn't x4 or the controller doesn't
      answer, it retries, up to `LWMR` (20) times.
    - `UPSB` has methods `SLMR` and `SFLG` that set the retry limit and
      flags to skip the checks. Nothing in the tables calls them, so
      they're probably for the macOS Thunderbolt driver.
    - The links are x4 at 8 GT/s now, so it's unclear which waits take the
      time.
17. Powering the first Thunderbolt chain down and up at runtime, without
    suspending, with `~/tb-runtime-test.sh`. The NHI (08:00.0) stays awake
    with or without its driver bound, so the script removes it, lets the
    xHCI (09:00.0) runtime suspend, waits for the whole chain to go to D3,
    then wakes the xHCI and rescans for the NHI. Waking the xHCI and its
    bridges took 5.9s, so the slow power-up happens without any suspend
    too. The rescan took 0.05s. The ACPI method trace logged nothing: the
    path has to be `\_SB_.PCI0...`, with the underscore padding. (Wrong:
    test 18 shows the tracer uses `\_SB.PCI0...`, so the reason is unknown.)
18. Same as 17, with ACPI tracing of all methods (`trace_state` `enable`)
    while waking up. `UPSB._PS0` took 5.9s:
    - `PCED`, the link retraining: 0.44s.
    - Then two `CRMW` calls, 2.7s each. `CRMW` does a read-modify-write of
      a Thunderbolt switch register (0x150 and 0x250, setting bit 26)
      through a mailbox in the bridge's PCI config space (`CIOR`, `CIOW`).
      Every `CIOR` timed out: it polls up to 10000 times with `Stall (25)`
      (0.44s in practice), and `CRMW` tries 5 times with `Sleep (100)`
      between. So the write never happens, it just costs 2.7s.
    - `NHI0._PS0` runs `PCED` and `CTBT`, which does one more `CRMW`
      (register 0x3C). That fits its 2.9s in test 14, and 0.44s + 2 x 2.7s
      fits the bridge's 6.3s.
19. Same as 18, with the `TbtPEG12` override from `acpi/` installed
    (`CRMW` tries once, `CIOR` and `CIOW` poll 400 times). The kernel logs
    `ACPI: Table Upgrade: override [SSDT-APPLE -TbtPEG12]`, revision
    00001001. `UPSB._PS0` took 0.47s instead of 5.9s: `PCED` 0.44s, and
    each `CRMW` 18ms, its one `CIOR` still timing out. The whole chain was
    back up in 0.49s.
20. Lid close with the override and `pm_print_times`, like test 14. Back
    after about 5s by the user's count. The device resume callbacks took
    4.0s in all instead of 21.5s, and the suspend ones 2.2s as before. Over
    0.1s, resume:

    | Device | Test 14 | Now |
    |---|---|---|
    | 06:00.0, Thunderbolt 3 bridge | 6.3s | 0.48s |
    | 7c:00.0, the other Thunderbolt 3 bridge | 6.3s | 0.48s |
    | 08:00.0 and 7e:00.0, the NHIs | 2.9s each | under 0.1s |
    | amdgpu (`pci_pm_resume`) | 1.2s | 1.2s |
    | 00:1c.0, the wifi's root port | 1.0s | 1.0s |

    00:1c.0 also still takes 1.0s to suspend, and amdgpu 0.5s.

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
- Suspend on lid close works: `lid-blank-screen` suspends after turning the
  screen off, if the Radeon is on, the lid is still closed and it isn't
  docked. The Radeon check reads its PCI vendor ID, since `power_state` says
  D3hot, not D3cold, when amdgpu-off has cut its power.
- Waking takes about 23s, and we don't know yet whether the firmware or
  Linux spends it. What we know:
  - By the wall clock, the time comes after the wake-up trigger. `rtcwake -s
    30` came back after 56s, not after 30s.
  - The kernel's own timestamps put a gap of the same size at a different
    place: between `smpboot: CPU 15 is now offline` and `Freezing user space
    processes`, on the way into suspend. 23.8s in test 10, 27.6s in tests 5
    and 6. Everything after that gap, through the resume, looks like it took
    under 0.25s.
  - Those timestamps can't be trusted there. In test 3 (`pm_test=devices`,
    no real S3), the gap was 7.0s, but the 5s `pm_test` wait, which comes
    after `Freezing user space processes`, doesn't show up after it. So time
    spent later gets logged at that point. The same could be true for the
    wake delay.
  - Linux spends the time, not the firmware: `pm_test=core` has the same
    delay (test 12), and it stops before the real sleep. With
    `pm_test=devices` (test 3) the extra time was only about 2s. So the
    delay comes from the `platform` level (test 13): the late and noirq
    device callbacks, and the ACPI `_PTS` and `_WAK` methods.
  - It's the noirq resume of the two Thunderbolt 3 controllers (test 14):
    18.4s. With `pm_async=off` the kernel runs them one after the other.
  - Almost all of that is the ACPI `CRMW` method timing out, 2.7s per
    call, three calls per controller (test 18). The mailbox it uses never
    answers. Maybe on macOS it does, because its Thunderbolt driver is up,
    or macOS never gets there.
  - It's not bringing the CPUs back up (test 11), and not the early CPU
    offlining either: the gap is just as long without it.
- Others see the same thing on T2 Macs:
  - [t2linux/kernel#30](https://github.com/t2linux/kernel/issues/30), open: a
    MacBookPro15,2 on linux-t2 7.2.4 and 7.2.6 has a fixed 22.6s gap in the
    same place, and waits about 22s for the screen after opening the lid. It
    blames t2linux/linux-t2-patches#52, "ACPI: x86: Apple T2 systems need
    early CPU offlining". That patch is what offlines the CPUs before
    `Freezing user space processes` here too.
  - [The resume that took a
    minute](https://kait2en.org/blog/the-resume-that-took-a-minute.html):
    bringing each CPU back up after S3 took several seconds on T2 Macs, so
    30s to 90s in all. The fix was offlining the CPUs early, which became
    the patch above. It also needed `pci=noaer` for a 19.6s EC wait, which
    doesn't apply here: the EC comes back in 28ms.
- The Radeon has to be on for suspend to work. Awake, that's about 21 W
  instead of about 7 W, much more than suspend could save. So suspend is only
  worth using with the amdgpu fix below.

## Next

- Find out why waking takes about 23s. macOS wakes up immediately, so it's
  possible. It was mostly the ACPI `CRMW` method timing out in the
  Thunderbolt controllers' `_PS0` methods (test 18). With the `acpi/`
  override, waking takes about 5s (test 20). Next:
  - Why the mailbox never answers: on t2linux/kernel#30, someone with a
    MacBookPro16,1 traced it to an ACPICA bug. ACPICA takes a PCI bridge's
    bus number from the bridge's own primary bus register, which reads 0
    right after D3cold, so the Thunderbolt bridge's `PCI_Config` region
    gets cached as 00:00.0 and the mailbox commands go to the wrong device.
    Their fix, [open-acpica/acpica#1236](https://github.com/open-acpica/acpica/pull/1236),
    was closed unmerged, with a t2linux maintainer saying the Apple
    Thunderbolt ACPI paths need reverse engineering first. They got resume
    from about 22.5s to 6.2s with it, and to 1.2–2.4s with more patches.
    The `acpi/` override is a workaround for the same thing: the mailbox
    commands still go to the wrong device, just fewer of them.
  - What's left: the wifi's root port (1.0s each way), amdgpu (1.2s) and
    the Thunderbolt link retraining in `PCED` (0.44s per controller).
  - Drop `pm_async=off` from `/etc/default/grub`, so the two controllers
    resume at the same time. That should save about 9s. It's there from the
    t2linux setup, but the current t2bce driver may not need it. It could
    change the i915 and gmux resume order.
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
