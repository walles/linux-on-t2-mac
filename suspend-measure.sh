#!/bin/sh
# Measure power use in suspend to RAM: battery charge before and after an hour
# asleep. The screen is turned off first and on after, like on lid close.
#
# Run unplugged, with the lid open: sudo sh ./suspend-measure.sh
# Results are appended to ~/suspend-measure.log, synced after every line, so
# they survive the battery running out.

B=/sys/class/power_supply/BAT0
LOG=/home/johan/suspend-measure.log
SECONDS_ASLEEP=3600

log() {
  echo "$*" | tee -a "$LOG"
  sync
}

set_power_save() {
  # 0 = on, 3 = off
  runuser -u johan -- env XDG_RUNTIME_DIR=/run/user/1000 \
    busctl --user set-property org.gnome.Mutter.DisplayConfig \
    /org/gnome/Mutter/DisplayConfig org.gnome.Mutter.DisplayConfig \
    PowerSaveMode i "$1"
}

# Prints: unix time, charge in µAh, voltage in µV
battery() {
  echo "$(date +%s) $(cat $B/charge_now) $(cat $B/voltage_now)"
}

if [ "$(id -u)" -ne 0 ]; then
  echo "Run as root: sudo sh $0" >&2
  exit 1
fi

if [ "$(cat /sys/class/power_supply/ADP1/online)" != 0 ]; then
  echo "Unplug the power first" >&2
  exit 1
fi

touch "$LOG"
chown johan: "$LOG"

log "=== $(date '+%F %T'), $(uname -r), asleep for ${SECONDS_ASLEEP}s"
log "awake draw: current_now=$(cat $B/current_now) uA voltage_now=$(cat $B/voltage_now) uV"
BEFORE=$(battery)
log "before: $BEFORE"

set_power_save 3
sleep 2
rtcwake -m mem -s "$SECONDS_ASLEEP"
AFTER=$(battery)
set_power_save 0
log "after: $AFTER"

# Use the average voltage for the energy
echo "$BEFORE $AFTER" | awk '{
  hours = ($4 - $1) / 3600
  wh = ($2 - $5) / 1e6 * ($3 + $6) / 2 / 1e6
  printf "result: %.2f Wh used in %.2f h asleep, about %.2f W\n", wh, hours, wh / hours
}' | tee -a "$LOG"
sync

# In case the battery gauge lags after the resume. Awake, this drains much
# faster than asleep, so it's only for comparing with the "after" reading.
sleep 120
log "2 min after: $(battery)"
