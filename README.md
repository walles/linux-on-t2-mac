# Outages for Linux on Johan's macBook

Sorted in priority order. Once something works, move to DONE.

## TODO

- Firefox loses its session on shutdown and brings up the restore page on
  the next boot. SIGTERM kills it without saving, a Firefox bug, sent as
  https://bugzilla.mozilla.org/show_bug.cgi?id=2086801. See
  `firefox-session.md`.
- Retry focus-follows-mouse with auto-raise once mutter `50.1-0ubuntu2.5`
  reaches `resolute-updates`. First try failed since focus jumped back to the
  window under the pointer after Cmd-Tab, a mutter bug fixed in that version.
  See `focus-follows-mouse.md`.
- Consider the threat model for LUKS. The only thing I could imagine is the
  computer being stolen and possibly examined by an unskilled attacker. Maybe
  they'd boot from their own live USB and try to access data. Then decide on
  where to go, dummy password like now or a real one?
- Suspend to RAM with the Radeon off. Now it only works with the Radeon on,
  which costs about 15 W extra while awake. See `suspend-notes.md`.
  deqrocks has dGPU power management working on 16,x, unreleased so far:
  https://github.com/open-acpica/acpica/pull/1236#issuecomment-5927183157
- Proper quick wakeup: https://github.com/open-acpica/acpica/pull/1236
- Get the apple-gmux patch merged, so the screen comes back after
  suspending with the screen on, like from the GNOME menu. Tested and
  working, sent as https://github.com/t2linux/linux-t2-patches/pull/74.
  Once merged, update the wiki's "Suspend workaround" section. See
  `black-screen-after-resume.md`.
- Doing `git commit` brings up a notification saying VSCode is ready, and VSCode
  shows up behind some other windows. Can we make the window move to the front
  in this case? Some discussion here:
  https://github.com/ghostty-org/ghostty/discussions/5812#discussioncomment-18709875
  Also, Claude had some suggestion about a EDITOR wrapper for this specific case.
- Better automatic screen brightness: fix GNOME's smoothing upstream, and
  maybe a power-law mapping. See "Improving it" in `auto-brightness.md`.
- The screen comes back very bright after GNOME blanks it. The gmux
  brightness register is reset to 80% while the screen is off, and the
  kernel doesn't notice. See `bright-screen-after-blank.md`.

# DONE

- Plugging in the charger with the lid closed woke the machine, and it then
  stayed awake all night with the lid closed, getting warm. Now
  `lid-blank-screen` suspends again after any wake with the lid closed. See
  `wake-with-lid-closed.md`.
- Screen brightness kept changing on its own. GNOME's Automatic Screen
  Brightness was following a coarse, flapping light sensor. Turned it off.
  Notes in `auto-brightness.md`.
- Daily automatic upgrades. Ubuntu's `unattended-upgrades` skipped every run
  because the machine is always on battery. Now runs on battery when above
  30%, and retries when getting online. See `auto-upgrades.md`.
- Make "Generating locales" faster by removing unused language packs. Notes in
  `locales.md`.
- Make both Cmd keys act as Ctrl, while keeping Cmd-Tab for switching apps and
  single / double tap of right Cmd for the overview / desktop picker. Setup in
  `keyboard-mappings.md`.
- Can we get the GNOME clock to show seconds?
- Suspend to RAM on lid close. And wake back up on lid open with everything
  working. Specifically, keyboard, trackpad, wifi, touch bar.
  - `files/usr/local/bin/lid-blank-screen` turns the screen off and then
    suspends, but only with the Radeon on. The screen has to be off before
    suspending, otherwise it stays black after the resume.
- Wake up from suspend quickly. Takes about 5s now, down from 23s.
  - Fixed by the Thunderbolt ACPI table override in `acpi/`, installed by
    `install-fixes.sh`. See `suspend-notes.md`.
- GNOME thinks I have a mouse, not a trackpad. Can't two finger scroll or
  two-finger click for right click. GNOME settings say nothing about
  trackpads.
  - Works out of the box with the T2 kernel, where `hid-magicmouse` drives the
    trackpad. On the fallback Ubuntu kernel it's a plain mouse.
- Inserting my USB drive should make it accessible in Linux
  - Fixed by `files/etc/udev/rules.d/90-t2-usbc-hotplug.rules`: the USB-C
    xHCI controllers runtime-suspended and never woke on plug-in, since Apple
    firmware lacks the ACPI links for that. Now they're kept powered on.
- The quick wake and USB drive fixes are both installed with
  `sudo ./install-fixes.sh`.
- Get a terminal program that can do split panes. And can search in the
  infinite scrollback buffer of each tab / pane. No terminal multiplexer.
  - Ghostty (`apt install ghostty`). `~/.config/ghostty/config.ghostty` sets
    `scrollback-limit = 1000000000`, 1 GB per pane, allocated lazily. Truly
    unlimited scrollback isn't supported by Ghostty yet, maintainer comment:
    https://github.com/ghostty-org/ghostty/discussions/8593
- Install vscode, set as default editor
- Want to be able to close lid and open it again after a minute. Computer
  should be alive and healthy with keyboard, wifi and things working.
  Whatever is easiest, even if power consumption is still on lid-open levels.
- Hard code password "empty" in initrd somewhere so I don't have to type it
  at boot. If we at some point go for a real password, the hard coded password
  would have to go.
- Lower power consumption with lid open. Read something about graphics and
  things needing some parameter somewhere to fix battery usage.
- Redo ~/src/twin's has-arrow-keys-emulation detection based on that Windows
  Terminal person's suggestion. This should make PTYXIS work OOTB, and we need
  to regression test it against whatever else we have. Skip as much per-terminal
  logic as possible.
