# Keyboard Mappings

Goal: both Cmd keys act as Ctrl, while keeping Cmd-Tab for switching apps and
single / double tap of right Cmd for the overview / desktop picker.

## Setup

Applied and working. Log out and back in for the `xkb-options` change to take
effect.

```
# Both Cmd keys act as Ctrl: left Cmd is Control_L, right Cmd is Control_R
gsettings set org.gnome.desktop.input-sources xkb-options "['altwin:ctrl_win']"

# Cmd-Tab switches apps
gsettings set org.gnome.desktop.wm.keybindings switch-applications "['<Control>Tab']"
gsettings set org.gnome.desktop.wm.keybindings switch-applications-backward "['<Shift><Control>Tab']"

# Unbind Alt-Tab. With it bound, Ctrl-Tab brought up the window switcher
# instead of the app switcher, for unknown reasons.
gsettings set org.gnome.desktop.wm.keybindings switch-windows "[]"
gsettings set org.gnome.desktop.wm.keybindings switch-windows-backward "[]"

# Tap right Cmd for the overview. Not left Cmd, since the physical Ctrl key
# also sends Control_L.
gsettings set org.gnome.mutter overlay-key 'Control_R'
```

Undo with `gsettings reset <schema> <key>`.

## Caveats

- GNOME grabs Ctrl-Tab and apps don't get it. Fine, it was never used.
- Alt-Tab (Option-Tab) does nothing. Fine, it was never used.
- Cmd-Tab switches apps, not windows. Windows would be preferred, but arrow
  keys pick among an app's windows, good enough for now.
- In terminals, Cmd-C sends Ctrl-C (interrupt) rather than copying. Use
  Ctrl-Shift-C / Ctrl-Shift-V.
- All other Super shortcuts are gone, for example Super-L to lock the screen
  (use the menu), Super-drag to move windows, Super-arrows for tiling and
  Super-. for emoji.

## Alternative: Toshy

[Toshy](https://github.com/RedBearAK/toshy) does Mac-style remapping that keeps
Super for GNOME and makes Cmd-C copy in terminals too. Not chosen because it's
much heavier: not in apt, needs sudo, udev rules, systemd user services and a
GNOME Shell extension, and brings lots of other Mac-isms.
