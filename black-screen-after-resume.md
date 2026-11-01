# Black screen after resume

On T2 kernels before 7.3.1-2, suspending with the screen on, like from the
GNOME menu or with `rtcwake`, gave a black screen after the resume.
Keyboard, touch bar and everything else came back. Turning the screen off
and on again brought it back.

Fixed in the T2 kernel 7.3.1-2: on 2026-11-01, five suspends in a row with
the screen on all came back, with `apple_gmux.force_igd=y` and no i915
errors. apple_gmux didn't change between v7.2 and v7.3, but i915 got many
link training and link recovery changes, probably one of those. Not
bisected.

## Cause, before 7.3.1-2

The gmux switches the internal panel between the Intel GPU and the Radeon.

1. During S3, the firmware switches the panel to the Radeon.
2. On resume, i915 sets up the panel. It's switched away, so i915 gets AUX
   timeouts and the link training fails. i915 gives up after about 3s and
   keeps drawing to a dead link. It only logs this with `drm.debug`.
3. Then the stock apple_gmux resumes and switches the panel back to the
   Intel GPU. Too late, i915 doesn't try again.

apple_gmux restores the switch in the normal `.resume` phase. The PCI
devices are registered before the gmux PNP device, so with `pm_async=off`
i915 resumes first.

If it comes back, the apple_gmux patch in
https://github.com/t2linux/linux-t2-patches/pull/74 (closed) fixed it on
7.2: it restores the switch in `.resume_early` and waits 200 ms for the
panel's AUX channel.
