# Outages for Linux on this macBook

Sorted in priority order. Once something works, move to DONE.

## TODO

- Want to be able to close lid and open it again after a minute. Computer
  should be alive and healthy with keyboard, wifi and things working.
  Whatever is easiest, even if power consumption is still on lid-open levels.
- Lower power consumption with lid open. Read something about graphics and
  things needing some parameter somewhere to fix battery usage.
- Suspend to RAM on lid close. And wake back up on lid open with everything
  working. Specifically, keyboard, trackpad, wifi, touch bar.
- Get a terminal program that can do split panes. And can search in the
  infinite scrollback buffer of each tab / pane.

# DONE

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
