#!/usr/bin/env python3
"""Pair each "looks good" note from the walk with the backlight level and the
median sensor reading over the preceding 20 s."""
import bisect
import csv
import statistics

L = [(float(r["boot_s"]), float(r["lux"])) for r in csv.DictReader(open("walk.csv"))
     if r["lux"] and r["note"] != "cached"]
B = [tuple(map(float, l.split(","))) for l in open("walk-backlight.csv") if "," in l]
# Notes may contain commas, so only split off the first two fields
N = [dict(zip(("boot_s", "wall", "note"), l.rstrip("\n").split(",", 2)))
     for l in list(open("walk-notes.csv"))[1:]]
bt = [b[0] for b in B]


def backlight(t):
    return B[max(bisect.bisect_right(bt, t) - 1, 0)][1] / 655.35


def sensor(t, win=20):
    vals = [l for tt, l in L if t - win <= tt <= t]
    # The sensor only reports changes, so the reading before the window
    # still holds at its start
    prev = [l for tt, l in L if tt < t - win]
    if prev:
        vals.append(prev[-1])
    if not vals:  # note logged before the first reading
        vals = [l for tt, l in L if t <= tt <= t + win]
    return statistics.median(vals), min(vals), max(vals)


if __name__ == "__main__":
    print(f"{'time':8} {'place':46} {'backlight':>9} {'sensor':>9} {'min..max':>18}")
    for n in N:
        if "looks good" not in n["note"]:
            continue
        t = float(n["boot_s"])
        m, lo, hi = sensor(t)
        print(f"{n['wall'][11:]:8} {n['note'][:46]:46} {backlight(t):8.1f}% "
              f"{m:9.0f} {f'{lo:.0f}..{hi:.0f}':>18}")
