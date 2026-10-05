# Automatic Upgrades

Goal: security upgrades get installed in the background every day, even though
this laptop isn't up at any fixed time of day and is always on battery while in
use.

Status: installed 2026-10-05. The first run upgraded 163 packages, and the
retry when getting online is verified.

## How Ubuntu does it

Stock Ubuntu already has this set up:

- `unattended-upgrades` is installed, and `/etc/apt/apt.conf.d/20auto-upgrades`
  turns on daily package list updates and daily unattended upgrades.
- `apt-daily.timer` refreshes the package lists, twice a day with up to 12 h
  random delay.
- `apt-daily-upgrade.timer` installs the upgrades, at 06:00 with up to 60 min
  random delay.
- Both timers have `Persistent=true`, so a run missed while the machine was off
  or suspended happens soon after the next boot or resume. That covers the "no
  fixed uptime" part.
- Only the Ubuntu release and `-security` pockets are upgraded automatically.
  `-updates`, the T2 kernel repo and VS Code still need a manual `apt upgrade`.

## The problem

Both services have `ConditionACPower=true`, and `unattended-upgrades` itself
defaults to `Unattended-Upgrade::OnlyOnACPower "true"`. Since the machine is
always on battery while in use, every run was skipped:

```
apt-daily-upgrade.service - Daily apt upgrade and clean activities skipped, unmet condition check ConditionACPower=true
```

Check with:

```
journalctl -u apt-daily.service -u apt-daily-upgrade.service
```

The AC adapter reporting itself is fine: `/sys/class/power_supply/ADP1/online`
just reads `0` because the adapter really isn't connected.

## Setup

Instead of requiring AC power, run on AC or with at least 30% battery, and only
when online. Retry whenever we get online.

- `files/etc/systemd/system/apt-daily.service.d/on-battery.conf` and
  `files/etc/systemd/system/apt-daily-upgrade.service.d/on-battery.conf`
  clear `ConditionACPower` and add two `ExecCondition`s:
  - `/sys/class/power_supply/BAT0/capacity` is at least 30%, or we're on AC.
    systemd has no configurable battery level condition of its own,
    `systemd-ac-power --low` has a fixed threshold.
  - `nmcli networking connectivity` says `full`. Without this, an offline run
    marks the day as done: `apt-get update` exits 0 even when no source is
    reachable, and `unattended-upgrade` then finds nothing new and succeeds.
    `apt.systemd.daily` skips steps whose stamp in `/var/lib/apt/periodic/` is
    from today (calendar day, not 24 h), so nothing would happen until
    tomorrow.

  A failing `ExecCondition` makes systemd skip the run cleanly, not mark it as
  failed, and it runs before `ExecStartPre`. So an offline run doesn't wait for
  the stock `apt-helper wait-online` 30 s timeout either.
- The `apt-daily-upgrade` drop-in also runs `dpkg --configure -a` first, if the
  dpkg journal in `/var/lib/dpkg/updates/` is dirty. If dpkg was interrupted,
  by the battery dying for example, `apt.systemd.daily`'s `apt-get check`
  fails and it exits before `unattended-upgrade` gets to run that itself.
  Automatic upgrades would then silently stop until a manual
  `sudo dpkg --configure -a`.
- `files/etc/apt/apt.conf.d/51unattended-upgrades-on-battery` turns off
  `OnlyOnACPower`. It has to sort after `50unattended-upgrades`.
- `files/etc/NetworkManager/dispatcher.d/90-apt-daily` starts both services
  when an interface comes up, or connectivity becomes full. The timers often
  fire right after resume, before the wifi is back, and then get skipped by the
  connectivity check. Starting the services often is harmless, since steps
  already done today are skipped. This also retries runs that were skipped
  because of low battery.

## Dry run without installing

```
# The battery and connectivity checks, in a throwaway user unit. Should print
# MAIN, change "30" to "101" or "full" to "nope" and it should be skipped.
systemd-run --user --wait --quiet \
  -p "ExecCondition=/bin/sh -c 'systemd-ac-power || [ \"\$\$(cat /sys/class/power_supply/BAT0/capacity)\" -ge 30 ]'" \
  -p "ExecCondition=/bin/sh -c '[ \"\$\$(nmcli networking connectivity)\" = full ]'" \
  /bin/echo MAIN
journalctl --user -n3

# The dispatcher hook, with a fake systemctl that just prints what it would do
mkdir -p /tmp/fakebin
printf '#!/bin/sh\necho "WOULD RUN: systemctl $*"\n' > /tmp/fakebin/systemctl
chmod +x /tmp/fakebin/systemctl
sed 's|/usr/bin/systemctl|/tmp/fakebin/systemctl|' files/etc/NetworkManager/dispatcher.d/90-apt-daily > /tmp/fakebin/hook
sh /tmp/fakebin/hook wlp5s0 up
CONNECTIVITY_STATE=FULL sh /tmp/fakebin/hook none connectivity-change
CONNECTIVITY_STATE=LIMITED sh /tmp/fakebin/hook none connectivity-change

# The apt setting, without installing it
APT_CONFIG=$PWD/files/etc/apt/apt.conf.d/51unattended-upgrades-on-battery apt-config dump | grep OnlyOnAC

# unattended-upgrade on battery, downloads but doesn't install. Doesn't touch
# the stamps, but does write to /var/log/unattended-upgrades/.
sudo APT_CONFIG=$PWD/files/etc/apt/apt.conf.d/51unattended-upgrades-on-battery unattended-upgrade --dry-run --debug
```

## Install

Install, then catch up on the backlog right away:

```
sudo install -v -D -m644 -t /etc/systemd/system/apt-daily.service.d files/etc/systemd/system/apt-daily.service.d/on-battery.conf
sudo install -v -D -m644 -t /etc/systemd/system/apt-daily-upgrade.service.d files/etc/systemd/system/apt-daily-upgrade.service.d/on-battery.conf
sudo install -v -m644 files/etc/apt/apt.conf.d/51unattended-upgrades-on-battery /etc/apt/apt.conf.d/
sudo install -v -m755 files/etc/NetworkManager/dispatcher.d/90-apt-daily /etc/NetworkManager/dispatcher.d/
sudo systemctl daemon-reload
sudo systemctl start apt-daily.service apt-daily-upgrade.service
```

Verify, on battery since being on AC skips the battery check:

```
# Should show the two ExecCondition lines and the dpkg ExecStartPre line
systemctl cat apt-daily-upgrade.service | grep -E 'ExecCondition|dpkg'

# Should show a run, or "Skipped due to 'exec-condition'" below 30% or offline
sudo systemctl start apt-daily-upgrade.service
journalctl -u apt-daily-upgrade.service -n5

# The stamps are empty files, check that their dates are today
ls -l --time-style=full-iso /var/lib/apt/periodic/

# Should exist and have entries from today
cat /var/log/unattended-upgrades/unattended-upgrades.log
```

If `journalctl` shows runs but the log stops getting new entries, something
else is blocking it.

To test the retry when getting online:

1. Remove today's stamps so there is something to do. They get recreated.
   `sudo rm /var/lib/apt/periodic/update-stamp /var/lib/apt/periodic/upgrade-stamp`
2. Turn the wifi off, then run
   `sudo systemctl start apt-daily.service apt-daily-upgrade.service`.
   `journalctl -u apt-daily.service -u apt-daily-upgrade.service -n5` should
   say "Skipped due to 'exec-condition'", and the stamps should still be gone.
3. Turn the wifi back on. Within a minute the same `journalctl` should show
   both services running, and the stamps should be back.

Undo by deleting the four installed files and the two `.service.d`
directories, then running `sudo systemctl daemon-reload`.

## Caveats

- A run skipped because of low battery is only retried on the next timer slot
  or the next time we get online, not when plugging in.
- If the network goes away in the middle of `apt-get update`, it still exits
  0 and the day is marked as done. Rare, so not handled.
  `APT::Update::Error-Mode "any"` would handle it, but then one flaky third
  party repo (VS Code, T2) would make every run fail.
- The hook fires for every interface that comes up, also `lo`. Harmless, the
  connectivity check and the stamps make those runs no-ops.
- Runs stop on metered connections, for example phone tethering if
  NetworkManager flags it as metered. Upstream default, kept on purpose.
- Nothing stops a run that has started if the battery drops below 30%, and
  lid-close suspend just pauses dpkg until resume. Runs are short, and suspend
  uses about 0.52 W, so this should be fine.
- A security update to dracut, systemd or firmware rebuilds the initramfs. The
  T2 config lives in `/etc/dracut.conf.d/` so it should survive, but the checks
  in `install-fixes.sh` don't run. It did survive the dracut upgrade on
  2026-10-05. To check by hand before rebooting, the first should list
  `tbt-peg12.aml`, and the second should list `bcm5974` before `t2bce_vhci`:
  `sudo lsinitrd /boot/initrd.img-$(uname -r) | grep tbt-peg12.aml`
  `sudo lsinitrd -f etc/cmdline.d/20-force_drivers.conf /boot/initrd.img-$(uname -r)`
- The T2 kernel repo isn't in `Allowed-Origins`, so kernels are never
  upgraded automatically. No automatic reboots either, `Automatic-Reboot`
  defaults to false.
- Getting online fires the hook twice, once for `up` and once for
  `connectivity-change`. The second start can begin `apt-daily` while
  `apt-daily-upgrade` is already running. Harmless, `apt.systemd.daily`
  serializes them on `/var/lib/apt/daily_lock`.
- BAT0 is hard coded. If it's missing, runs on battery are skipped.
- The threshold is hard coded to 30% in both drop-ins.
