# Focus Follows Mouse

Goal: the window under the pointer gets focus, and is raised after a short
delay.

Status: tried and rejected for now, see [Why it was rejected](#why-it-was-rejected).
Reverted to GNOME's default click-to-focus with `gsettings reset`. Retry once
the mutter fix is out, see [Upstream](#upstream).

## Setup

Takes effect immediately, works on Wayland.

```
# Focus follows the pointer, but stays put when the pointer is over the
# desktop or the top bar
gsettings set org.gnome.desktop.wm.preferences focus-mode sloppy

# Raise the focused window after 500 ms
gsettings set org.gnome.desktop.wm.preferences auto-raise true
gsettings set org.gnome.desktop.wm.preferences auto-raise-delay 500
```

Undo with `gsettings reset <schema> <key>`.

## How the delays work

There are two stages, only the second one has a configurable delay:

1. Focus: with `org.gnome.mutter focus-change-on-pointer-rest` (default true),
   focus changes only once the pointer stops moving over a window, not on
   entry. The rest threshold isn't configurable, only on / off.
2. Raise: `auto-raise-delay` counts from when the window got focus. If focus
   moves elsewhere before then, the raise is cancelled.

So sweeping the pointer across windows on the way somewhere else changes
neither focus nor stacking.

## Decisions

- `sloppy` rather than `mouse`: `mouse` drops focus when the pointer leaves
  all windows, for example when reaching for the top bar.
- 500 ms raise delay is the GNOME default. Try 300 if it feels sluggish, or
  800+ if windows pop up too eagerly.

## Why it was rejected

Keyboard window switching fights with the pointer:

1. VSCode full screen, a smaller terminal behind it on the left part of the
   screen, the pointer to the right.
2. Cmd-Tab to the terminal. It gets focus and is raised, but the pointer is
   now over VSCode, outside the terminal.
3. The pointer moves the least bit, focus goes back to VSCode, and VSCode is
   auto-raised over the terminal again.

So every Cmd-Tab also needed the pointer moved into the target
window. See [Upstream](#upstream) below, this is a fixed mutter bug.

### Upstream

This is a mutter 50 regression, not inherent to focus follows mouse. Before
50, keyboard focus stuck until the pointer entered another window.

- Upstream bug: https://gitlab.gnome.org/GNOME/mutter/-/work_items/4479
- Fixed in mutter 50.2 by
  https://gitlab.gnome.org/GNOME/mutter/-/merge_requests/5036
- Ubuntu bug: https://bugs.launchpad.net/bugs/2152847
  - Fix committed for 26.04 as mutter `50.1-0ubuntu2.5`, in `resolute-proposed`
    as of 2026-10-17. This machine has `50.1-0ubuntu2.4`.
  - Upgrading from `-proposed` needs all three of
    `libmutter-18-0 mutter gir1.2-mutter-18` at once, or apt removes `gdm3`.
  - One tester says keyboard tiling (Tiling Assistant) still makes focus jump
    back to the window under the pointer.

Worth trying again once `50.1-0ubuntu2.5` or later reaches `resolute-updates`.
