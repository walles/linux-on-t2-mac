#!/usr/bin/env python3
"""Replay the walk through simulate.py's algorithms and write everything the
chart page needs as one JSON file.

Usage: export-chart-data.py <out.json>
"""

import json
import math
import sys

import calibration
import simulate as S

ANCHOR = 6.0

raw = S.read_recording("walk.csv")
t0 = raw[0][0]
readings = [(t - t0, lux) for t, lux in raw]
end = readings[-1][0]
notes = S.read_notes("walk-notes.csv")
good = [(max(t - t0, 0.0), n) for t, _, n in notes if "looks good" in n]
moving = [t - t0 for t, _, n in notes if n.startswith("moving")]

results = [
    S.stock(readings, ANCHOR),
    S.proposed_linear(readings, ANCHOR),
    S.proposed_power(readings, ANCHOR),
]
short = ["Stock GNOME 50", "Fixed timing", "Power law"]


def next_after(ts, t, default=end):
    return min([x for x in ts if x > t], default=default)


summaries = []
for r, name in zip(results, short):
    errors = []
    for t, _ in good:
        if t > 1:
            user = calibration.backlight(t + t0)
            errors.append(abs(math.log(max(r.at(t), 0.5) / max(user, 0.5))))
    stay_changes = stay_wakeups = 0
    for t, _ in good:
        nxt = next_after(moving, t)
        stay_changes += S.changes_between(r.out, t, nxt, r.at(t))
        stay_wakeups += sum(1 for w in r.timer_times if t < w <= nxt)
    up, down = [], []
    for m in moving:
        g = next_after([g for g, _ in good], m, None)
        if g is None:
            continue
        nm = next_after(moving, g)
        lag = S.reaction_lag(r, readings, m, nm)
        if lag is None:
            continue
        (up if r.at(nm) > r.at(m) else down).append(round(lag))
    summaries.append({
        "name": name,
        "description": r.name,
        "typical_error": math.exp(sorted(errors)[len(errors) // 2]),
        "stay_changes": stay_changes,
        "reversals": S.reversals(r.out, 1.0),
        "writes": len(r.out),
        "timer_wakeups": r.timer_wakeups,
        "stay_wakeups": stay_wakeups,
        "lag_up": up,
        "lag_down": down,
    })

# The user's real backlight, only where it changed
user_trace = []
for t, v in calibration.B:
    pct = round(v / 655.35, 2)
    if not user_trace or user_trace[-1][1] != pct:
        user_trace.append([round(t - t0, 2), pct])

data = {
    "duration_s": end,
    "start_wall": notes[0][1],
    "anchor_pct": ANCHOR,
    "readings": [[round(t, 2), lux] for t, lux in readings],
    "user": user_trace,
    "notes": [[round(max(t - t0, 0.0), 2), n] for t, _, n in notes],
    "looks_good": [
        [round(t, 2), n.split(";")[0], round(calibration.backlight(t + t0), 2),
         round(calibration.sensor(t + t0)[0])] + [round(r.at(t), 2) for r in results]
        for t, n in good
    ],
    "series": [
        {"name": n, "points": [[round(t, 2), round(v, 3)] for t, v in r.out]}
        for r, n in zip(results, short)
    ],
    "summaries": summaries,
}

with open(sys.argv[1], "w") as f:
    json.dump(data, f, separators=(",", ":"))
for s in summaries:
    print(s)
