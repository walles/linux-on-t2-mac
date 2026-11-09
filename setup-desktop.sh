#!/bin/bash
# Set up the desktop for the logged in user: keyboard, GNOME settings, Ghostty
# and VS Code as the editor. Run from a terminal in the GNOME session, as
# yourself, after sudo ./setup-system.sh. Safe to run again. Log out and back
# in afterwards.
set -euo pipefail

if [ "$(id -u)" -eq 0 ]; then
    echo "Run as yourself, not as root" >&2
    exit 1
fi

cd "$(dirname "$0")/files/home"

# Copy a file from files/home/ to ~, leaving it alone if it has local changes
put() {
    if [ ! -e ~/"$1" ]; then
        install -v -D -m644 "$1" ~/"$1"
    elif ! cmp -s "$1" ~/"$1"; then
        echo "NOT UPDATED, has local changes: ~/$1" >&2
        echo "  Compare with: diff $PWD/$1 ~/$1" >&2
    fi
}

#
# Keyboard, see keyboard-mappings.md
#

gsettings set org.gnome.desktop.input-sources sources "[('xkb', 'se+mac')]"

# Left Option-7 for | and \
put .config/xkb/rules/evdev
put .config/xkb/types/johan
put .config/xkb/symbols/johan

# Both Cmd keys act as Ctrl
gsettings set org.gnome.desktop.input-sources xkb-options "['altwin:ctrl_win', 'johan:lalt7']"

# Cmd-Tab switches apps
gsettings set org.gnome.desktop.wm.keybindings switch-applications "['<Control>Tab']"
gsettings set org.gnome.desktop.wm.keybindings switch-applications-backward "['<Shift><Control>Tab']"
gsettings set org.gnome.desktop.wm.keybindings switch-windows "[]"
gsettings set org.gnome.desktop.wm.keybindings switch-windows-backward "[]"

# Tap right Cmd for the overview
gsettings set org.gnome.mutter overlay-key 'Control_R'

# Free Cmd-Option-Left/Right for switching tabs
gsettings set org.gnome.desktop.wm.keybindings switch-to-workspace-left "['<Super>Page_Up', '<Super>KP_Prior', '<Super><Alt>Left']"
gsettings set org.gnome.desktop.wm.keybindings switch-to-workspace-right "['<Super>Page_Down', '<Super>KP_Next', '<Super><Alt>Right']"

#
# GNOME
#

# The light sensor makes automatic brightness jumpy, see auto-brightness.md
gsettings set org.gnome.settings-daemon.plugins.power ambient-enabled false

gsettings set org.gnome.desktop.interface clock-show-seconds true

#
# Apps
#

put .config/ghostty/config.ghostty
put .config/Code/User/keybindings.json

# VS Code as the editor, -w waits for the file to be closed
if ! grep -qs '^export EDITOR=' ~/.profile; then
    cat >>~/.profile <<'EOF'

# Use VS Code as editor, -w waits for the file to be closed
export EDITOR="code -w"
export VISUAL="$EDITOR"
EOF
fi

xdg-mime default com.microsoft.VSCode.desktop \
    text/plain application/x-zerosize \
    text/x-python text/x-python3 text/x-go text/rust text/x-rust \
    text/x-csrc text/x-chdr text/x-c++src text/x-c++hdr

echo "OK. Log out and back in."
