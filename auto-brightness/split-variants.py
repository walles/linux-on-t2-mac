#!/usr/bin/env python3
"""Replay the walk through each part of the proposed gsd change on its own,
to see which part is worth an MR by itself. Run from this directory.

Usage: split-variants.py
"""

import math

import simulate as sim

def stock_deadzone(readings, anchor, rel=0.10):
    """Stock timing and mapping, but only send when the target moved more
    than rel times the last target sent. No timer."""
    r = sim.Result(f"stock + dead zone {rel:.0%}")
    norm = None; acc = -1.0; last = None; sent = None
    slider = sim.slider_for(anchor)
    for t, lux in readings:
        if lux <= 0: continue
        if norm is None:
            norm = lux * sim.NORMALIZE_CONSTANT; acc = 100 / sim.NORMALIZE_CONSTANT
        alpha = 0.0 if last is None else 1 / (1 + sim.STOCK_TAU_S / (t - last))
        last = t
        b = min(max(lux * 100 / norm, 0), 100)
        acc = alpha * b + (1 - alpha) * acc
        # Same test as GSD_AMBIENT_TARGET_THRESHOLD in the gsd patch
        if sent is None or abs(acc - sent) > sent * rel:
            sent = acc
            r.emit(t, sim.shell_backlight(acc, slider))
    return r

def timing_only(readings, anchor, tau=sim.STOCK_TAU_S):
    """Fixed timing + timer, stock tau, no real dead zone (0.1 pp)."""
    slider = sim.slider_for(anchor)
    p = sim.Proposed(f"timing fix only, tau {tau:.1f}", sim.gsd_linear,
                     lambda pct: sim.shell_backlight(pct, slider), tau, tau, 0.1)
    return p.run(readings)

def timing_relzone(readings, anchor, tau, rel=0.10):
    slider = sim.slider_for(anchor)
    p = sim.Proposed(f"timing + dead zone {rel:.0%}, tau {tau:g}", sim.gsd_linear,
                     lambda pct: sim.shell_backlight(pct, slider), tau, tau,
                     math.log(1 + rel), domain="log")
    return p.run(readings)


def main():
    raw = sim.read_recording("walk.csv"); t0 = raw[0][0]
    rd = [(t - t0, l) for t, l in raw]
    a = 6.0
    res = [sim.stock(rd, a), stock_deadzone(rd, a), timing_only(rd, a),
           timing_relzone(rd, a, sim.STOCK_TAU_S), timing_relzone(rd, a, 10.0)]
    sim.evaluate(res, rd, sim.read_notes("walk-notes.csv"), t0)


if __name__ == "__main__":
    main()
