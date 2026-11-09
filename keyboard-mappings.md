# Keyboard Mappings

Goal: both Cmd keys act as Ctrl, while keeping Cmd-Tab for switching apps and
single / double tap of right Cmd for the overview / desktop picker. Left
Option-7 types `|` and left Option-Shift-7 types `\`, like on macOS, while left
Option stays Alt for everything else.

## Setup

Applied and working, by `setup-desktop.sh`. Log out and back in for the
`xkb-options` change to take effect.

```
# Both Cmd keys act as Ctrl: left Cmd is Control_L, right Cmd is Control_R.
# johan:lalt7 is left Option-7, see below.
gsettings set org.gnome.desktop.input-sources xkb-options "['altwin:ctrl_win', 'johan:lalt7']"

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

## Left Option-7 for `|` and `\`

In the `se+mac` layout `|` and `\` are on the third and fourth levels of the 7
key, which only right Option reaches. Making all of left Option a third-level
key (`lv3:lalt_switch`) would lose Alt shortcuts everywhere, so instead a custom
XKB option gives only the 7 key a key type where Alt picks those levels.

GNOME on Wayland reads user XKB files from `~/.config/xkb`. `setup-desktop.sh`
copies them there from `files/home/.config/xkb/` and enables `johan:lalt7`.

- `rules/evdev` includes the system rules and adds the `johan:lalt7` option
- `types/johan` defines `JOHAN_ALT_FOUR_LEVEL`: like `FOUR_LEVEL`, but Alt also
  picks level 3 / 4
- `symbols/johan` gives the 7 key that type

Alt is consumed on that key, so Ghostty sees a plain `|` rather than Alt-`|`.
Firefox and VS Code don't: left Option-7 types nothing there, with or without
Shift, and in Firefox doesn't switch to tab 7 either. Use right Option-7 in
those.

## Switching tabs

The same keys in Ghostty, Firefox and VS Code:

- Cmd-Option-Left / Right: previous / next tab
- Option-1 … Option-8: go to tab 1 … 8, out of the box

GNOME's default for previous / next tab is Ctrl-PageUp / PageDown (Cmd-Fn-Up /
Down here), which still works but goes up / down for something left / right.

`setup-desktop.sh` sets this up, except for Firefox:

- GNOME: removes Ctrl-Alt-Left / Right from switching workspaces. Three-finger
  swipes still do that.
- Ghostty: `files/home/.config/ghostty/config.ghostty`. Replaces moving between
  splits left / right.
- VS Code: `files/home/.config/Code/User/keybindings.json`. Replaces moving the
  editor to the previous / next group.
- Firefox: by hand, install the
  [Hotkeys to Switch Tabs Left and Right](https://addons.mozilla.org/firefox/addon/hotkeys-for-tabs-left-right/)
  extension, which defaults to Ctrl-Alt-Left / Right. `about:keyboard` can't
  change tab switching, it doesn't list it.

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
