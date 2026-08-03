#!/usr/bin/env python3
"""
Wind-wave estimator for Quidi Vidi Lake (Royal St. John's Regatta course).

Fetch-limited wave growth: on a small lake the wave height at any point is set by
how far the wind has blown over open water *upwind of that point* (the fetch).
For a wind blowing down the long (≈E-W) axis of the pond, the fetch at the
windward (upwind) end is ~0 and grows to the full lake length at the leeward end.

Course geometry (start/finish at the WEST end; crews row EAST to the buoys):
    start / finish .............. 0 m      (windward end under a WESTERLY)
    women's turn (halfway) ...... 600 m
    men's turn (foot of pond) ... 1200 m   (leeward end under a WESTERLY)

Method: deep-water fetch-limited JONSWAP relations (Hasselmann et al. 1973, as
given in the USACE Coastal Engineering Manual):

    Hm0 = 0.0016 (gF/U^2)^0.5 · U^2/g      significant wave height
    Tp  = 0.286  (gF/U^2)^(1/3) · U/g       peak period

capped at the fully-developed limits (Hm0=0.243 U^2/g, Tp=8.134 U/g).
U is the 10 m wind speed. Depth-limitation is negligible here: the waves are so
short (Tp ~ 1-2 s, wavelength < ~5 m) that anything deeper than ~2 m is
effectively deep water, and the QV course is deeper than that.
"""
from __future__ import annotations
import argparse, math

G = 9.81
# Course sample points (m of fetch when wind blows straight down the pond)
POINTS = [("Start/finish (windward end)", 100.0),   # ~0; use 100 m so it's non-degenerate
          ("Women's turn / halfway", 600.0),
          ("Men's turn buoys (foot)", 1200.0),
          ("Full-lake fetch", 1600.0)]
AXIS_LEN = 1600.0      # lake long-axis length (m)
CROSS_FETCH = 300.0    # approx lake width -> fetch cap for cross-axis winds (m)
AXIS_BEARING = 100.0   # course axis ~ WNW-ESE; treat as 100/280 deg line


def wave(u_ms: float, fetch_m: float):
    """Return (Hm0 metres, Tp seconds) for wind speed u (m/s) and fetch (m)."""
    if u_ms <= 0 or fetch_m <= 0:
        return 0.0, 0.0
    xstar = G * fetch_m / u_ms**2
    Hm0 = min(0.0016 * xstar**0.5, 0.243) * u_ms**2 / G
    Tp  = min(0.286 * xstar**(1/3.), 8.134) * u_ms / G
    return Hm0, Tp


def eff_fetch(fetch_axis_m: float, wind_from_deg: float | None) -> float:
    """Reduce along-axis fetch for winds not aligned with the pond axis.
    First-order: F_eff = F·cos(alpha) (alpha = angle off axis), floored by the
    cross-lake width fetch. Winds square to the axis are width-limited (~300 m)."""
    if wind_from_deg is None:
        return fetch_axis_m
    # angle between wind direction and the axis line (0 or 180 both align)
    a = abs((wind_from_deg - AXIS_BEARING + 90) % 180 - 90)
    along = fetch_axis_m * max(math.cos(math.radians(a)), 0.0)
    return max(along, min(CROSS_FETCH, fetch_axis_m) * math.sin(math.radians(a)))


def kmh(ms): return ms * 3.6
def ms(kmh): return kmh / 3.6


def table(winds_kmh):
    print(f"{'Wind (km/h)':>12s} | " + " | ".join(f"{n.split('(')[0].strip():>22s}" for n,_ in POINTS))
    print(f"{'':>12s} | " + " | ".join(f"{'Hs cm / Tp s':>22s}" for _ in POINTS))
    print("-"*(15+len(POINTS)*25))
    for w in winds_kmh:
        cells=[]
        for _,F in POINTS:
            H,T=wave(ms(w),F)
            cells.append(f"{H*100:6.0f} cm / {T:3.1f} s ".rjust(22))
        print(f"{w:>12.0f} | " + " | ".join(cells))


def main():
    ap=argparse.ArgumentParser(description=__doc__,
        formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument("--wind", type=float, help="wind speed km/h (single scenario)")
    ap.add_argument("--dir", type=float, default=None,
                    help="wind FROM direction deg (e.g. 270=W). Applies directional fetch.")
    args=ap.parse_args()

    if args.wind is not None:
        print(f"Quidi Vidi wave estimate — wind {args.wind:.0f} km/h"
              + (f" from {args.dir:.0f}deg" if args.dir is not None else " (straight down pond)"))
        print(f"{'Course point':32s}{'fetch m':>9s}{'Hs cm':>8s}{'Tp s':>7s}")
        for name,F in POINTS:
            Fe=eff_fetch(F,args.dir)
            H,T=wave(ms(args.wind),Fe)
            print(f"{name:32s}{Fe:9.0f}{H*100:8.0f}{T:7.1f}")
    else:
        print("Fetch-limited significant wave height (Hs) & peak period (Tp),")
        print("wind blowing straight down the pond (worst case: W or E wind):\n")
        table([10,15,20,25,30,40,50,60])
        print("\nRule of thumb: rowing shells with low freeboard get uncomfortable")
        print("around Hs ~ 12-15 cm; ~20 cm+ is rough / unfair; the far (leeward)")
        print("turn is always the worst spot under an along-pond wind.")


if __name__=="__main__":
    main()
