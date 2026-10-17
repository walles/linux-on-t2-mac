#!/bin/bash
# Run a locally built gsd-power in place of the system one, with automatic
# brightness on, then restore everything.
#
# Usage: run-gsd-power.sh <gsd-power binary> <seconds> <log file>
set -u
BIN=$1
SECS=$2
LOG=$3
SCHEMA=org.gnome.settings-daemon.plugins.power

restore() {
    gsettings set $SCHEMA ambient-enabled false
    systemctl --user start org.gnome.SettingsDaemon.Power.service
}
trap restore EXIT

systemctl --user stop org.gnome.SettingsDaemon.Power.service
gsettings set $SCHEMA ambient-enabled true
G_MESSAGES_DEBUG=all timeout "$SECS" "$BIN" 2>&1 \
    | while IFS= read -r line; do printf '%s %s\n' "$(date +%T.%3N)" "$line"; done \
    > "$LOG"
