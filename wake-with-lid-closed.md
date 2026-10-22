# Waking up with the lid closed

The machine was warm in the morning after charging overnight. It had been
awake all night with the lid closed and the screen off, drawing about 15-20 W
inside the closed case.

## Cause

`lid-blank-screen` used to suspend only when the lid *changed* to closed.
logind ignores the lid (`/etc/systemd/logind.conf.d/lid-ignore.conf`), so
nothing suspended the machine again if something else woke it while the lid
stayed closed.

Plugging in the charger wakes the machine from S3. The battery switches to
`charging` in the same second as the kernel's `PM: suspend exit`, and there's
no `Lid opened` event.

## The night of 2026-10-16

| Time  | Event                                                           |
| ----- | --------------------------------------------------------------- |
| 23:09 | Lid closed, `lid-blank-screen` suspends                         |
| 23:10 | Charger plugged in, machine wakes up, lid still closed          |
| 23:45 | Battery full                                                    |
| 11:24 | Lid opened. Awake for over 12 hours, mostly at 100% on the charger |

The same happened three times earlier that day, at 07:18, 18:22 and 21:47,
all charger plug-ins.

Being awake costs about 15-20 W, since the Radeon has to stay on for suspend
to work (see `suspend-notes.md`). UPower showed 16.6 W right after opening the
lid.

Sitting warm at 100% for hours is also bad for the battery. UPower reports
its health at 80.6% of design capacity.

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

## Workaround

Plug in the charger first, then close the lid. On 2026-10-15 at 22:27 the
machine was suspended while already charging and slept 8 hours until the lid
opened, through the battery reaching full. Unclear whether unplugging while
asleep wakes it, so open the lid first.

## Possible fixes

- In `lid-blank-screen`, also listen for logind's `PrepareForSleep(false)`
  signal, sent on resume. If the lid is still closed, the Radeon is on and
  it isn't docked, suspend again. This handles any wake source, not just the
  charger. To avoid a suspend loop, it stays awake if it re-suspended less
  than a minute ago. Implemented and tested on 2026-10-17: lid closed, charger
  plugged in, the machine woke at 13:08:11, logged "Woke up with the lid
  closed, suspending again" and was asleep again at 13:08:38. It then slept
  until the lid opened at 13:13:35, and that wake stayed awake. The lid state
  is read from `/proc/acpi/button/lid/LID0/state`, since UPower may still say
  closed right after a lid-open wake.
- Asking GNOME to lock an already locked screen never answers, and `busctl`
  gives up after 25 s. That was the 26 s before suspending again. So
  `lid-blank-screen` only locks if the screen isn't locked already.
- Suspending can be refused. On 2026-10-22 at 00:06 the charger woke the
  machine, the wake started the overdue daily apt jobs, and apt 3.2 blocks
  suspend while installing (`DPkg::Inhibit-Sleep`). Suspending at 00:07:19
  failed with "Operation denied due to active block inhibitor", and the
  machine stayed awake with the lid closed until 17:17. Now `lid-blank-screen`
  retries every 30 s while the lid is closed, and gives up when it opens. It
  doesn't override blockers, since interrupting an install would be worse.
- Stop the charger from waking the machine at all. Not investigated. None of
  the entries in `/proc/acpi/wakeup` is obviously the power adapter, so it may
  be the SMC or the firmware doing it.

## Related: charge limit

macOS can stop charging at 80% to save the battery. Not available here yet:
`BAT0` has no `charge_control_end_threshold`, and `applesmc` is loaded but has
no device bound. macOS does this through an SMC key (`BCLM` on Intel Macs,
maybe `CHWA` on newer firmware). Not verified on this T2 machine.
