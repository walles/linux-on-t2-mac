#!/bin/sh
# Measure power use in suspend to RAM: battery charge before and after some
# minutes asleep, 8 hours by default. The screen is turned off first and on
# after, like on lid close.
#
# Run unplugged, with the lid open: sudo sh ./suspend-measure.sh [minutes]
# Try 1 minute first, to see that it wakes up. That result means nothing.
# Results are appended to ~/suspend-measure.log, synced after every line, so
# they survive the battery running out.
#
# Going to sleep and waking up take about 10s at awake power, and the battery
# gauge can re-estimate its charge after a long rest. Both matter less the
# longer the sleep, so sleep for hours, not minutes.

B=/sys/class/power_supply/BAT0
LOG=/home/johan/suspend-measure.log
MINUTES=${1:-480}
SECONDS_ASLEEP=$((MINUTES * 60))

log() {
  echo "$*" | tee -a "$LOG"
  sync
}

set_power_save() {
  # 0 = on, 3 = off
  runuser -u johan -- env XDG_RUNTIME_DIR=/run/user/1000 \
    busctl --user set-property org.gnome.Mutter.DisplayConfig \
    /org/gnome/Mutter/DisplayConfig org.gnome.Mutter.DisplayConfig \
    PowerSaveMode i "$1" || log "WARNING: setting PowerSaveMode to $1 failed"
}

# Prints: unix time, charge in µAh, voltage in µV
battery() {
  echo "$(date +%s) $(cat $B/charge_now) $(cat $B/voltage_now)"
}

# For explaining odd results, not used in the calculation
context() {
  echo "($(cat $B/capacity)%, $(cat $B/status)," \
    "current_now=$(cat $B/current_now) uA)"
}

if [ "$(id -u)" -ne 0 ]; then
  echo "Run as root: sudo sh $0" >&2
  exit 1
fi

if [ "$(cat /sys/class/power_supply/ADP1/online)" != 0 ]; then
  echo "Unplug the power first" >&2
  exit 1
fi

if [ "$(cat $B/capacity)" -lt 30 ]; then
  echo "Battery below 30%, charge it first" >&2
  exit 1
fi

touch "$LOG"
chown johan: "$LOG"

log "=== $(date '+%F %T'), $(uname -r), asleep for ${MINUTES} min"
BEFORE=$(battery)
log "before: $BEFORE $(context)"

set_power_save 3
sleep 2
rtcwake -m mem -s "$SECONDS_ASLEEP"
STATUS=$?
AFTER=$(battery)
log "after: $AFTER $(context), rtcwake exit status $STATUS"
set_power_save 0

# Use the average voltage for the energy. Less than 95% of the planned time
# means the suspend failed or something woke the machine up early.
echo "$BEFORE $AFTER $SECONDS_ASLEEP" | awk '{
  seconds = $4 - $1
  if (seconds < 0.95 * $7)
    printf "WARNING: only %d s of the planned %d s\n", seconds, $7
  if (seconds <= 0)
    exit
  hours = seconds / 3600
  wh = ($2 - $5) / 1e6 * ($3 + $6) / 2 / 1e6
  printf "result: %.2f Wh used in %.2f h asleep, about %.2f W\n", wh, hours, wh / hours
}' | tee -a "$LOG"
sync

# In case the battery gauge lags after the resume. Awake, this drains much
# faster than asleep, so it's only for comparing with the "after" reading.
sleep 120
log "2 min after: $(battery) $(context)"
