# Auto-brightness dead zone: replay results

Evidence for the gnome-settings-daemon change "power: Ignore small changes in
the ambient light target": only send a new target to the shell when it
differs from the last one sent by more than 10%.

## What was recorded

A MacBook Pro 2019 (MacBookPro16,1) on 2026-10-17, with automatic brightness off. For 20
minutes I walked between a badly lit room, a dark room, a well lit room and
outside. At each place I set the brightness by hand and noted when it looked
right, and I noted when I started moving again.

- [`walk.csv`](walk.csv): every `LightLevel` update from iio-sensor-proxy,
  637 readings, 3 of them 0 (gsd ignores those). The sensor reports at most
  every 0.8 s, and only when the value changes. In steady light it
  alternates between neighbouring values, up to about 7% apart.
- [`walk-notes.csv`](walk-notes.csv): the "looks good" and "moving" notes.
  They reached the recorder a few seconds late.
- [`walk-backlight.csv`](walk-backlight.csv): the backlight, polled every
  0.5 s.

## What was replayed

- Stock: a Python port of `iio_proxy_changed()` from gsd 50.0 (the same on
  51.1), plus gnome-shell's backlight = target + slider − 50%.
  `simulate.py --selftest` checks the port against hand-worked values.
- Dead zone: the same, with the check from the gsd change.

The slider is all the way left, the closest the shell gets to the 6% I had
chosen at the start. So the backlight is gsd's target − 50%, between 0 and
50%.

Code: `stock()` in [`simulate.py`](simulate.py), `stock_deadzone()` in
[`split-variants.py`](split-variants.py).

## Results

| | Stock | Dead zone |
|---|---|---|
| Backlight changes while standing still | 31 | 3 |
| Updates sent to the shell | 634 | 32 |

- Standing still: from each "looks good" note to the next "moving" note,
  389 s in total over 10 stays. A change is a backlight step of at least 0.5
  percentage points and 5%.
- Reaction to real changes: on the 6 moves where the backlight changed, it
  got 90% of the way to its new level at the same time as stock, within
  1 s. On the other 2 it stayed at its 50% maximum.

To reproduce, in this directory: `python3 split-variants.py`.
