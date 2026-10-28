# Firefox Session After Shutdown

Goal: Firefox shuts down cleanly on logout and shutdown, so the next start
brings back the open tabs without the "Restore Session" page.

Status: Firefox bug, reported as
https://bugzilla.mozilla.org/show_bug.cgi?id=2086801.

## What happens

On GNOME Wayland nothing asks Firefox to quit. It runs in its own scope under
`user@1000.service`, so it lives until systemd stops the user manager and
sends it SIGTERM. That happens after GNOME Shell has already exited:

```
08:41:15.327  gnome-shell: Shutting down GNOME Shell
08:41:15.822  systemd --user: Stopping snap.firefox.firefox-….scope
08:41:15.931  Stopped snap.firefox.firefox-….scope
```

Firefox dies on SIGTERM without saving. Since bug 1837907 it was supposed to
quit cleanly, but that patch calls `nsAppShell::InstallTermSignalHandler()`
from the end of `XRE_mainStartup()`, before the app shell exists, so the
handler is never installed. The only SIGTERM handler left is the profile
lock's, which restores the default and re-raises. Firefox 122.0 and 157.0.1
behave the same, both the snap and Mozilla's own build.

The next start then sees a crash. Firefox restores silently only if the
session is less than six hours old and the start before wasn't also a
crash. Otherwise it shows `about:sessionrestore`, which is what you get
after a night's shutdown. The tabs aren't lost: Firefox saves them to
`sessionstore-backups/recovery.jsonlz4` every 15 seconds.

## Reproducing without logging out

```sh
D=~/snap/firefox/common/fftest; mkdir -p $D
firefox --new-instance --profile $D about:robots & sleep 12
kill -TERM $(pgrep -f "/snap/firefox/.*profile $D" -o)
cat $D/sessionCheckpoints.json; ls $D/sessionstore*
```

A clean exit writes `sessionstore.jsonlz4` and ends the checkpoints with
`sessionstore-final-state-write-complete`. After SIGTERM the checkpoints stop
at `sessionstore-windows-restored` and there is no `sessionstore.jsonlz4`.

## Workaround

Settings → General → Startup → "Open previous windows and tabs"
(`browser.startup.page = 3`). Firefox then restores silently after an unclean
exit too, losing at most the last 15 seconds.

## Even with the fix

SIGTERM arrives after GNOME Shell, and with it the Wayland display, is gone.
If Firefox can't quit cleanly without a display, the next step is to have
it hear about the session ending earlier, for example through the desktop
portal's session state monitor.
