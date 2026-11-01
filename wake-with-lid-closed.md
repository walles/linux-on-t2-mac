# Waking up with the lid closed

Plugging in the charger wakes the machine from S3, with the lid closed. The
battery switches to `charging` in the same second as the kernel's
`PM: suspend exit`, and there's no `Lid opened` event. Awake, it draws about
15-20 W inside the closed case, since the Radeon has to stay on for suspend
to work (see `suspend-notes.md`).

logind handles this: after any wake with the lid still closed, it suspends
again once its 30 s `HoldoffTimeoutSec` has passed. Tested on 2026-11-01
with the charger: woke at 15:25:16, asleep again at 15:25:40, and stayed
asleep until the lid opened. With `LidSwitchIgnoreInhibited=no` it also
waits for anything blocking suspend, like apt, and suspends once that's
done (logind rechecks the lid after every event while it's closed).

## How to check

Suspend and wake events, look for `suspend exit` without a `Lid opened` just
before it:

```sh
journalctl --since yesterday -o short-iso |
  grep -E 'PM: suspend (entry|exit)|Lid (opened|closed)'
```

Charger plug-ins, from UPower's history, as state changes only:

```sh
awk '{ if ($3 != prev) print; prev = $3 }' \
  /var/lib/upower/history-charge-*-99.dat |
  while read -r t v s; do echo "$(date -d @"$t" +%FT%T) $v $s"; done |
  tail -20
```

Wakeup sources enabled in ACPI, all of them are on:

```sh
grep enabled /proc/acpi/wakeup
```

## Possible fix

Stop the charger from waking the machine at all. Not investigated. None of
the entries in `/proc/acpi/wakeup` is obviously the power adapter, so it may
be the SMC or the firmware doing it.

## Related: charge limit

macOS can stop charging at 80% to save the battery. Sitting warm at 100% for
hours is bad for it; UPower reports its health at 80.6% of design capacity.
The battery, from the `macsmc-power` driver, has
`charge_control_end_threshold`. It read `0` on 2026-11-01. Not tried yet.
Find the battery in `/sys/class/power_supply/` by `type` `Battery`, the
kernel picks the name. macOS does this through an SMC key (`BCLM` on Intel
Macs, maybe `CHWA` on newer firmware). Not verified on this T2 machine.
