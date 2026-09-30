# Outages for Linux on this macBook

Sorted in priority order. Once something works, move to DONE.

## TODO

- Wake up from suspend quickly. Now it takes about 23s, and it's unclear
  whether that time goes to the firmware or to Linux. macOS wakes up
  immediately, so it's possible. See `suspend-notes.md`.
- Suspend to RAM with the Radeon off. Now it only works with the Radeon on,
  which costs about 15 W extra while awake. See `suspend-notes.md`.
- Get a terminal program that can do split panes. And can search in the
  infinite scrollback buffer of each tab / pane.
- Consider the threat model for LUKS. The only thing I could imagine is the
  computer being stolen and possibly examined by an unskilled attacker. Maybe
  they'd boot from their own live USB and try to access data. Then decide on
  where to go, dummy password like now or a real one?

# DONE

- Suspend to RAM on lid close. And wake back up on lid open with everything
  working. Specifically, keyboard, trackpad, wifi, touch bar.
  - `files/usr/local/bin/lid-blank-screen` turns the screen off and then
    suspends, but only with the Radeon on. The screen has to be off before
    suspending, otherwise it stays black after the resume.
- GNOME thinks I have a mouse, not a trackpad. Can't two finger scroll or
  two-finger click for right click. GNOME settings say nothing about
  trackpads.
  - Fixed by `files/etc/dracut.conf.d/89-t2-trackpad.conf`: the initramfs
    force-loads `apple-bce` for the LUKS prompt, which made `usbhid` claim the
    trackpad before `bcm5974` loaded. Now `bcm5974` is force-loaded first.
- Inserting my USB drive should make it accessible in Linux
  - Fixed by `files/etc/udev/rules.d/90-t2-usbc-hotplug.rules`: the USB-C
    xHCI controllers runtime-suspended and never woke on plug-in, since Apple
    firmware lacks the ACPI links for that. Now they're kept powered on.
- Both installed with `sudo ./install-fixes.sh`.
- Install vscode, set as default editor
- Want to be able to close lid and open it again after a minute. Computer
  should be alive and healthy with keyboard, wifi and things working.
  Whatever is easiest, even if power consumption is still on lid-open levels.
- Hard code password "empty" in initrd somewhere so I don't have to type it
  at boot. If we at some point go for a real password, the hard coded password
  would have to go.
- Lower power consumption with lid open. Read something about graphics and
  things needing some parameter somewhere to fix battery usage.
