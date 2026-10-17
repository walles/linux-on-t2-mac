#!/usr/bin/env python3
"""Replay recorded light readings through GNOME's auto-brightness and
proposed replacements, and compare the backlight levels they produce.

Usage:
  simulate.py <recording.csv> [--notes walk-notes.csv] [--anchor PCT]
              [--csv out.csv]
  simulate.py --selftest

The user sets the brightness once, to --anchor at the first reading, and
never touches it again. Each algorithm then decides the backlight for the
rest of the recording. With --notes, the backlight is compared against what
the user chose at each "looks good" note, and stays and moves are measured.

Models, from gnome-settings-daemon 50.0 (plugins/power/gsd-power-manager.c)
and gnome-shell 50.1 (js/misc/brightnessManager.js):

- gsd computes a target in percent from each LightLevel update and sends it
  with SetAutoBrightnessTarget.
- Shell sets backlight = clamp(target + slider - 50%, 0, 100%).
- Moving the slider makes gsd re-normalize, so that the current reading
  maps to a 66.7% target. Here that only happens once, at the start.
"""

import argparse
import csv
import math
import sys

# gsd 50.0
STOCK_TAU_S = 1.0 / (2.0 * math.pi * 0.1)  # 1.59 s
SEND_INTERVAL_S = 0.1
NORMALIZE_CONSTANT = 1.5


def read_recording(path):
    """Returns [(seconds, lux)], starting at 0. Keeps 0 readings."""
    with open(path) as f:
        rows = [(float(r.get("boot_s") or r["mono_s"]), float(r["lux"]))
                for r in csv.DictReader(f)
                if r["lux"] and r.get("note") != "cached"]
    return rows


def read_notes(path):
    # Notes may contain commas, so only split off the first two fields
    with open(path) as f:
        lines = f.readlines()[1:]
    notes = []
    for line in lines:
        boot_s, wall, note = line.rstrip("\n").split(",", 2)
        notes.append((float(boot_s), wall, note))
    return notes


def shell_backlight(target_pct, slider):
    return min(max(target_pct + 100.0 * slider - 50.0, 0.0), 100.0)


def slider_for(anchor_pct, target_pct=100.0 / NORMALIZE_CONSTANT):
    """The slider setting that gives anchor_pct right after normalization,
    clamped to what the slider can do."""
    return min(max((anchor_pct - target_pct + 50.0) / 100.0, 0.0), 1.0)


class Result:
    def __init__(self, name):
        self.name = name
        self.out = []  # (t, backlight percent), each a write
        self.timer_wakeups = 0
        self.timer_times = []

    def emit(self, t, pct):
        if self.out and t - self.out[-1][0] < SEND_INTERVAL_S:
            self.out[-1] = (self.out[-1][0], pct)
        else:
            self.out.append((t, pct))

    def at(self, t):
        """Backlight in effect at time t."""
        value = None
        for tt, v in self.out:
            if tt > t:
                break
            value = v
        return value


def stock(readings, anchor_pct):
    """Port of iio_proxy_changed(): runs once per LightLevel update, no
    timer, then Shell adds the slider bias."""
    r = Result("stock GNOME 50")
    norm_value = None
    accumulator = -1.0
    last_update = None
    slider = None
    for t, lux in readings:
        if lux <= 0:
            continue
        if norm_value is None:
            norm_value = lux * NORMALIZE_CONSTANT
            if accumulator <= 0:
                accumulator = 100.0 / NORMALIZE_CONSTANT
            slider = slider_for(anchor_pct)
        if last_update is not None:
            alpha = 1.0 / (1.0 + STOCK_TAU_S / (t - last_update))
        else:
            alpha = 0.0
        last_update = t
        brightness = min(max(lux * 100.0 / norm_value, 0.0), 100.0)
        accumulator = alpha * brightness + (1.0 - alpha) * accumulator
        r.emit(t, shell_backlight(accumulator, slider))
    return r


class Proposed:
    """Event-driven smoothing with no polling.

    Each reading holds until the next, so between readings the average has a
    closed form: acc(t) = held + (acc0 - held) * exp(-dt / tau). Nothing
    happens until the average is more than `deadband` away from the value
    last sent. Then it follows the average, writing every `track_s`, until
    it has moved less than `settle` over the last `still_s` seconds, and goes
    idle again. (Not "until it reaches the reading": when the sensor
    alternates between two values, the reading never stops jumping, but the
    average does stop moving.) While idle, one timer is scheduled for when the
    average will cross the dead zone, if it ever will.

    Smoothing happens in the `domain` ("linear" percent, or "log" percent so
    that dead zone and smoothing are relative).
    """

    def __init__(self, name, mapping, compose, tau_up, tau_down, deadband,
                 domain="linear", settle=None, track_s=0.5, still_s=3.0):
        self.result = Result(name)
        self.mapping = mapping  # (lux, first_lux) -> target pct, or None
        self.compose = compose  # target pct -> backlight pct
        self.tau_up = tau_up
        self.tau_down = tau_down
        self.deadband = deadband
        self.settle = settle if settle is not None else deadband / 4
        self.track_s = track_s
        self.still_s = still_s
        if domain == "log":
            self.f, self.finv = math.log, math.exp
        else:
            self.f, self.finv = (lambda x: x), (lambda x: x)

    def tau(self):
        return self.tau_up if self.held > self.acc0 else self.tau_down

    def acc_at(self, t):
        return self.held + (self.acc0 - self.held) * math.exp(
            -(t - self.t0) / self.tau())

    def output(self, t, value):
        self.sent = value
        self.result.emit(t, self.compose(self.finv(value)))

    def crossing_time(self, t):
        """When the average leaves the dead zone around `sent`, or None."""
        gap = self.held - self.sent
        if abs(gap) <= self.deadband:
            return None
        c = self.sent + math.copysign(self.deadband, gap)
        acc = self.acc_at(t)
        if (c - self.held) / (acc - self.held) >= 1:
            return t
        return t + self.tau() * math.log((acc - self.held) / (c - self.held))

    def evaluate(self, t):
        acc = self.acc_at(t)
        if self.tracking:
            self.output(t, acc)
            self.track_log.append((t, acc))
            earlier = [v for tt, v in self.track_log if tt <= t - self.still_s]
            converged = abs(acc - self.held) < self.settle
            still = earlier and abs(acc - earlier[-1]) < self.settle
            if converged or still:
                self.tracking = False
                self.wake_at = self.crossing_time(t)
            else:
                self.wake_at = t + self.track_s
        else:
            crossing = self.crossing_time(t)
            # At the edge of the dead zone, rounding can put acc just inside
            # it; count reaching the crossing time as crossing.
            if (abs(acc - self.sent) > self.deadband
                    or (crossing is not None and crossing <= t + 1e-6)):
                self.tracking = True
                self.track_log = [(t, acc)]
                self.output(t, acc)
                self.wake_at = t + self.track_s
            else:
                self.wake_at = crossing

    def fire_timers(self, until, inclusive=False):
        while self.wake_at is not None and (
                self.wake_at < until or (inclusive and self.wake_at <= until)):
            now = self.wake_at
            self.result.timer_wakeups += 1
            self.result.timer_times.append(now)
            self.evaluate(now)
            if self.wake_at is not None and self.wake_at <= now:
                raise RuntimeError(f"timer rescheduled to {self.wake_at} at {now}")

    def run(self, readings, end_t=None):
        first_lux = None
        self.wake_at = None
        self.tracking = False
        for t, lux in readings:
            self.fire_timers(t)
            if first_lux is None:
                if lux <= 0:
                    continue
                first_lux = lux
            target = self.mapping(lux, first_lux)
            if target is None:
                continue
            v = self.f(target)
            if not self.result.out:
                self.acc0 = self.held = v
                self.t0 = t
                self.output(t, v)
                continue
            # Advance the average over the time the previous reading held
            self.acc0 = self.acc_at(t)
            self.t0 = t
            self.held = v
            self.evaluate(t)
        self.fire_timers(end_t if end_t is not None else readings[-1][0],
                         inclusive=True)
        return self.result


def gsd_linear(lux, first_lux):
    """gsd's mapping, normalized at the first reading. Ignores 0."""
    if lux <= 0:
        return None
    return min(max(lux * 100.0 / (first_lux * NORMALIZE_CONSTANT), 0.0), 100.0)


def proposed_linear(readings, anchor_pct, tau=10.0, deadband=2.0, end_t=None):
    """Smallest change: gsd's mapping and Shell's bias kept, only the
    smoothing replaced."""
    slider = slider_for(anchor_pct)
    p = Proposed(f"fixed timing, tau {tau:g} s, dead zone {deadband:g} pp",
                 gsd_linear, lambda pct: shell_backlight(pct, slider),
                 tau, tau, deadband)
    return p.run(readings, end_t)


def proposed_power(readings, anchor_pct, exponent=0.4, floor_pct=1.0,
                   tau_up=3.0, tau_down=10.0, deadband_rel=0.10, track_s=1.0,
                   end_t=None):
    """Power-law mapping anchored at the user's setting, 0 counts as dark
    (floor), smoothing and dead zone relative, dimming slower."""
    floor_lux = None

    def mapping(lux, first_lux):
        nonlocal floor_lux
        if lux <= 0:
            return floor_pct
        return min(max(anchor_pct * (lux / first_lux) ** exponent, floor_pct),
                   100.0)

    p = Proposed(f"power law ^{exponent:g}, floor {floor_pct:g}%, "
                 f"tau {tau_up:g} s up / {tau_down:g} s down, "
                 f"dead zone {deadband_rel:.0%}",
                 mapping, lambda pct: pct, tau_up, tau_down,
                 math.log(1 + deadband_rel), domain="log", track_s=track_s)
    return p.run(readings, end_t)


# --- Evaluation --------------------------------------------------------------

def reversals(out, min_step):
    """Direction changes in the written values, ignoring steps < min_step."""
    count, direction, last = 0, 0, None
    for _, v in out:
        if last is None:
            last = v
            continue
        step = v - last
        if abs(step) < min_step:
            continue
        d = 1 if step > 0 else -1
        if direction and d != direction:
            count += 1
        direction, last = d, v
    return count


def changes_between(out, t_from, t_to, start_value):
    """Visible changes within a window: steps >= 0.5 pp and >= 5 %."""
    n, last = 0, start_value
    for t, v in out:
        if t_from < t <= t_to:
            if (last is not None and abs(v - last) >= 0.5
                    and abs(v - last) >= 0.05 * max(last, 1e-9)):
                n += 1
            last = v
    return n


def log_level(v):
    return math.log(max(v, 0.5))


def reaction_lag(r, readings, t_from, t_to):
    """How much later than the sensor the backlight gets 90% of the way.

    Within [t_from, t_to], one move and the stay after it: the sensor's
    change goes from the reading in effect at t_from to the median of the
    last 20 s before t_to. The backlight's change goes from its value at
    t_from to its value at t_to. For each, find when it first got 90% of the
    way, on a log scale. Returns None for changes under 10%."""
    before = [l for t, l in readings if t <= t_from]
    window = [l for t, l in readings if t_to - 20 <= t <= t_to] or \
             [l for t, l in readings if t <= t_to][-1:]
    if not before or not window:
        return None
    s0 = log_level(before[-1])
    s1 = log_level(sorted(window)[len(window) // 2])
    b0, b1 = r.at(t_from), r.at(t_to)
    if b0 is None or b1 is None:
        return None
    b0, b1 = log_level(b0), log_level(b1)
    if abs(s1 - s0) < 0.1 or abs(b1 - b0) < 0.1:
        return None

    def first_90(series, a, b):
        goal = a + 0.9 * (b - a)
        return next((t for t, v in series
                     if t_from < t <= t_to and (log_level(v) - goal) * (b - a) >= 0),
                    None)

    ts = first_90(readings, s0, s1)
    tb = first_90(r.out, b0, b1)
    if ts is None or tb is None:
        return None
    return tb - ts


def evaluate(results, readings, notes, t0):
    # A note can come just before the first reading; count it as at the start
    good = [(max(t - t0, 0.0), wall, n) for t, wall, n in notes
            if "looks good" in n]
    moving = [(t - t0, wall, n) for t, wall, n in notes if n.startswith("moving")]
    end = readings[-1][0]

    print("\nBacklight at each \"looks good\", versus what the user chose:\n")
    head = f"  {'time':8} {'place':30} {'user':>6}"
    for r in results:
        head += f" {r.name[:14]:>14}"
    print(head)
    import calibration  # noqa: E402  reuses the walk's backlight log
    errors = {r.name: [] for r in results}
    for t, wall, n in good:
        user = calibration.backlight(t + t0)
        line = f"  {wall[11:]:8} {n.split(';')[0][:30]:30} {user:5.1f}%"
        for r in results:
            v = r.at(t)
            line += f" {v:13.1f}%"
            if t > 1:  # skip the anchor itself
                # 0 % counts as 0.5 %, so a black screen counts as an error
                errors[r.name].append(abs(math.log(max(v, 0.5) / max(user, 0.5))))
        print(line)

    print("\nSummary:\n")
    for r in results:
        e = errors[r.name]
        typical = math.exp(sorted(e)[len(e) // 2]) if e else float("nan")
        stays = 0
        # A stay: from a "looks good" until the next "moving" (or the end)
        for t, _, _ in good:
            nxt = min([m for m, _, _ in moving if m > t], default=end)
            stays += changes_between(r.out, t, nxt, r.at(t))
        reacts = []
        for m, _, _ in moving:
            nxt_good = min([g for g, _, _ in good if g > m], default=None)
            if nxt_good is None:
                continue
            nxt_move = min([x for x, _, _ in moving if x > nxt_good], default=end)
            lag = reaction_lag(r, readings, m, nxt_move)
            if lag is not None:
                reacts.append(lag)
        in_stays = 0
        for t, _, _ in good:
            nxt = min([m for m, _, _ in moving if m > t], default=end)
            in_stays += sum(1 for w in r.timer_times if t < w <= nxt)
        print(f"  {r.name}")
        print(f"    typical error vs user:     x{typical:.2f}")
        print(f"    visible changes in stays:  {stays}")
        print(f"    up/down reversals >= 1 pp: {reversals(r.out, 1.0)}")
        if reacts:
            print(f"    lag behind the sensor:     "
                  + ", ".join(f"{x:+.0f}" for x in reacts) + " s")
        print(f"    backlight writes:          {len(r.out)}")
        print(f"    timer wakeups:             {r.timer_wakeups}"
              f" ({in_stays} during stays)")


def selftest():
    ok = True

    def check(what, got, want, tol):
        nonlocal ok
        good = abs(got - want) <= tol
        ok &= good
        print(f"{'ok  ' if good else 'FAIL'} {what}: got {got:.3f}, want {want:.3f}")

    check("stock time constant (s)", STOCK_TAU_S, 1.5915, 0.001)

    # Stock: steady light, then the reading doubles after 10 quiet seconds.
    # The new reading gets 1 / (1 + 1.59 / 10) = 86% of the weight. With the
    # slider at 50% there's no bias, so backlight == gsd's target.
    s = stock([(0.0, 1000.0), (10.0, 2000.0)], anchor_pct=100 / 1.5)
    base = 100 / 1.5
    check("stock first backlight (%)", s.out[0][1], base, 1e-6)
    check("stock weight of new reading after 10 s",
          (s.out[1][1] - base) / (100 - base), 1 / (1 + STOCK_TAU_S / 10), 1e-6)

    # Shell's bias: the slider can't take the backlight below target - 50.
    check("lowest backlight right after normalization (%)",
          shell_backlight(base, slider_for(0.0)), base - 50, 1e-6)

    # Proposed, no dead zone: at the new reading nothing has happened yet
    # (the 10 s were spent at the old value), then the timer converges on
    # 1 - exp(-t / tau).
    p = Proposed("t", lambda lux, f: lux / 20, lambda pct: pct, 2.0, 2.0,
                 deadband=0.01, settle=0.01, track_s=0.5)
    r = p.run([(0.0, 1000.0), (10.0, 2000.0)], end_t=30.0)
    check("proposed at the new reading (%)", r.at(10.0), 50.0, 1e-6)
    t_w, v_w = [(t, v) for t, v in r.out if t <= 15.0][-1]
    want = 100 - 50 * math.exp(-(t_w - 10.0) / 2.0)
    check(f"proposed {t_w - 10:.2f} s after the step (%)", v_w, want, 1e-6)
    check("proposed settles", r.out[-1][1], 100.0, 0.02)
    ok &= r.timer_wakeups > 0

    # Steady light: no timer wakeups at all
    p = Proposed("t", lambda lux, f: lux / 20, lambda pct: pct, 10.0, 10.0,
                 deadband=2.0)
    r = p.run([(i * 0.8, 1000.0) for i in range(100)])
    check("timer wakeups in steady light", r.timer_wakeups, 0, 0)

    # Flapping 20% every 0.8 s between targets 60% and 50%, dead zone 2 pp,
    # tau 10 s. It starts at 60% and should move once to the average, 55%,
    # then stay put: the average wiggles by much less than the dead zone.
    readings = [(i * 0.8, 1000.0 if i % 2 else 1200.0) for i in range(100)]
    p = Proposed("t", lambda lux, f: lux / 20, lambda pct: pct, 10.0, 10.0,
                 deadband=2.0)
    r = p.run(readings)
    late = [(t, v) for t, v in r.out if t > 40]
    check("writes while flapping, second half", len(late), 0, 0)
    check("level while flapping (%)", r.at(80.0), 55.0, 2.0)
    st = stock(readings, anchor_pct=100 / 1.5)
    print(f"     flapping: stock wrote {len(st.out)} times, "
          f"{reversals(st.out, 1.0)} reversals >= 1 pp")
    return ok


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("recording", nargs="?")
    ap.add_argument("--notes")
    ap.add_argument("--anchor", type=float, default=6.0,
                    help="backlight the user wants at the first reading, %%")
    ap.add_argument("--csv", help="write all backlight outputs here")
    ap.add_argument("--selftest", action="store_true")
    args = ap.parse_args()

    if args.selftest:
        sys.exit(0 if selftest() else 1)

    raw = read_recording(args.recording)
    t0 = raw[0][0]
    readings = [(t - t0, lux) for t, lux in raw]
    print(f"{len(readings)} readings over {readings[-1][0] / 60:.1f} min, "
          f"anchor {args.anchor:g}% at reading {readings[0][1]:.0f}")
    s = slider_for(args.anchor)
    print(f"stock: slider {s:.2f} gives {shell_backlight(100 / 1.5, s):.1f}% "
          f"at the anchor (wanted {args.anchor:g}%)")

    results = [
        stock(readings, args.anchor),
        proposed_linear(readings, args.anchor),
        proposed_power(readings, args.anchor),
    ]

    if args.notes:
        evaluate(results, readings, read_notes(args.notes), t0)
    else:
        for r in results:
            print(f"  {r.name}: {len(r.out)} writes, "
                  f"{reversals(r.out, 1.0)} reversals, "
                  f"{r.timer_wakeups} timer wakeups")

    if args.csv:
        with open(args.csv, "w") as f:
            w = csv.writer(f)
            w.writerow(["algorithm", "t_s", "backlight_pct"])
            for r in results:
                for t, v in r.out:
                    w.writerow([r.name, f"{t:.3f}", f"{v:.3f}"])


if __name__ == "__main__":
    main()
