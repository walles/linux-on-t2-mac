# Focus Follows Mouse

Goal: the window under the pointer gets focus, and is raised after a short
delay.

Status: not used. Nice on the second try, but it isn't GNOME's default, and
I mostly use full screen windows on this machine anyway, so it helps little. Reverted to click-to-focus with `gsettings reset`.

## Setup

Takes effect immediately, works on Wayland.

```
# Focus follows the pointer, but stays put when the pointer is over the
# desktop or the top bar
gsettings set org.gnome.desktop.wm.preferences focus-mode sloppy

# Raise the focused window, after auto-raise-delay (default 500 ms)
gsettings set org.gnome.desktop.wm.preferences auto-raise true
```

Undo with `gsettings reset <schema> <key>`.

## How the delays work

There are two stages, only the second one has a configurable delay:

1. Focus: with `org.gnome.mutter focus-change-on-pointer-rest` (default true),
   focus changes only once the pointer stops moving over a window, not on
   entry. "Stopped" means not moving for one 25 ms poll (`FOCUS_TIMEOUT_DELAY`
   in mutter's `src/core/display.c`), so even a brief pause counts. The rest
   threshold isn't configurable, only on / off.
2. Raise: `auto-raise-delay` counts from when the window got focus. If focus
   moves elsewhere before then, the raise is cancelled.

So sweeping the pointer across windows on the way somewhere else changes
neither focus nor stacking. Since the rest check is so short, the raise delay
is what keeps windows from popping up while passing over them.

## Decisions

- `sloppy` rather than `mouse`: `mouse` drops focus when the pointer leaves
  all windows, for example when reaching for the top bar.
- Keep GNOME's default 500 ms raise delay, don't override it. If it feels
  sluggish or too eager, set `auto-raise-delay`.

## Known issues

- Before mutter `50.1-0ubuntu2.5`, Cmd-Tab to a window not under the pointer
  lost focus again as soon as the pointer moved, and the window under the
  pointer was raised back over it. Mutter 50 regression,
  https://gitlab.gnome.org/GNOME/mutter/-/work_items/4479, fixed upstream in
  50.2 and in Ubuntu by https://bugs.launchpad.net/bugs/2152847.
- One tester on that Ubuntu bug says keyboard tiling (Tiling Assistant) still
  makes focus jump back to the window under the pointer. Not tried here.
