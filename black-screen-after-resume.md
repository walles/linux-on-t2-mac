# Black screen after resume

Suspending with the screen on, like from the GNOME menu or with `rtcwake`,
gives a black screen after the resume. Keyboard, touch bar and everything
else come back. Turning the screen off and on again brings it back, which is
why `lid-blank-screen` turns the screen off before suspending.

`kernel-patches/apple-gmux-resume-early.patch` fixes it. Tested with S3 on
this MacBookPro16,1 on 2026-10-18, see below. Hibernation and older Macs are
untested. Not sent upstream yet.

## Cause

The gmux switches the internal panel between the Intel GPU and the Radeon.

1. During S3, the firmware switches the panel to the Radeon.
2. On resume, i915 sets up the panel. It's switched away, so i915 gets AUX
   timeouts and the link training fails. i915 gives up after about 3s and
   keeps drawing to a dead link. It only logs this with `drm.debug`.
3. Then the stock apple_gmux resumes and switches the panel back to the
   Intel GPU. Too late, i915 doesn't try again.

Turning the screen off and on makes i915 train the link again, now with the
panel switched to it.

apple_gmux has restored the switch on resume since 2012, probably because
the firmware resets it on older Macs too. But it does it in the normal
`.resume` phase. The PCI devices are registered before the gmux PNP device,
so with `pm_async=off` i915 resumes first.

With the screen off at suspend, i915 has nothing to set up at resume. By
the time GNOME turns the screen on, the switch is right.

## The fix

In the patch, apple_gmux restores the switch in `.resume_early`, and in the
early phases of hibernation thaw and restore. All early resume callbacks are
done before any normal `.resume` starts, so the switch is in place before
i915 touches the panel, with or without `pm_async=off`.

Restoring the switch isn't enough by itself. The panel needs time after the
switch before it answers on the AUX channel. The patch waits 200 ms, which is
the maximum time eDP allows a panel from power on until AUX works (T3). It
only waits on T2 Macs, and only if the switch was changed during suspend.

## Measurements

From a test module with log lines, with `rtcwake -m mem -s 20` and the
screen on. gmux port 0x10 reads 4 when switched to the Intel GPU, 5 for the
Radeon.

- Before suspend 0x10 reads 4, and in `.resume_early` it reads 5. Every time.
- Restoring the switch in `.resume_early` without waiting: still black. i915
  starts 3 ms later and fails the same way.
- Waiting after the restore: 100 ms black, 175, 250, 400 ms and 1 s worked.
  One test each, so 200 ms has little margin.
- The patch with 200 ms: four out of four worked. i915 resumed in 0.27s,
  instead of failing for 3s.
- Port 0x11 reads 3 when switched to the Radeon, 1 right after switching to
  the Intel GPU, and 0 only once i915 has trained the link. It stayed at 1
  after the failed resumes. It follows i915, not the switch, so it can't be
  polled instead of sleeping.
- The gmux ACPI device (`APP000B`) has no power methods: no `power_state` in
  `/sys/bus/acpi/devices/APP000B:00/`. So it doesn't need the PNP resume
  that comes after `.resume_early` before it can be used.

## Trying the patch

apple_gmux is a module, so no kernel build or reboot is needed. Get
`drivers/platform/x86/apple-gmux.c` for the running kernel version, apply the
apple-gmux part of t2linux's
`2009-apple-gmux-allow-switching-to-igpu-at-probe.patch`, then this patch. In
a directory with the patched `apple-gmux.c`:

```sh
echo 'obj-m := apple-gmux.o' > Makefile
make -C /lib/modules/$(uname -r)/build M=$PWD modules
sudo rmmod apple_gmux && sudo insmod ./apple-gmux.ko
```

The stock module comes back at the next reboot. The brightness slider is
gone for a moment while the module is unloaded.

## Upstream

apple_gmux is maintained under X86 PLATFORM DRIVERS, Hans de Goede and Ilpo
Järvinen, list platform-driver-x86@vger.kernel.org. Worth a cc: Lukas
Wunner (vga_switcheroo) and Orlando Chamberlain (T2 gmux support).

The patch is against mainline and doesn't depend on the t2linux patch. It
needs a commit message with the measurements, and `git format-patch`
against the pdx86 `for-next` branch. Questions a reviewer may ask:

- Why hasn't this been seen on older Macs? The delay is T2 only, but the
  `.resume_early` move applies to all of them.
- Why not fix it in i915, or with a device link from i915 to the gmux? The
  gmux driver owns the switch the firmware changed, so it should restore it
  before anyone uses it. Separately, i915 silently gives up when AUX doesn't
  answer after a failed link training. That's an i915 issue.
- Does the gmux on older Macs work in `.resume_early`, before the PNP
  resume? Their ACPI devices may have power or resource methods.
