"""How far apart, IN WALL-CLOCK TIME, are the conjuncts G5 needs together?

This is a pure measurement. No detector is run, nothing is scored, and no verdict
moves. It answers one design question that decides whether the obvious repair to
G5 is viable at all:

    G5 requires recognition, norm and discount in ONE step. They never co-occur
    (see docs/G5_POSTMORTEM_STEP_LOCALITY_2026-09-10.md). The obvious repair is
    to accumulate them across the session instead. This project already ships
    that machinery -- engine/ring12/horizon.py, with a CALIBRATED half-life of
    3600s and time-based exponential decay.

    So: over what wall-clock interval would the accumulator have to hold
    evidence for the conjunction to close on this trajectory?

If the interval is long relative to the shipped 3600s half-life, then
session-scoping is NOT a free repair: the evidence from the earlier conjunct
would have decayed to near nothing before the later one arrives, and the
successor needs a different horizon -- which is a design decision that must be
made and registered on its own terms, not smuggled in.

Reusing the SHIPPED half-life matters. Inventing a window after having seen that
recognition sits at step 11 and the discount at step 406 would be tuning to the
answer. The shipped constant was calibrated for a different purpose, before this
transcript existed.

Canary: timestamps and deltas only; no transcript text.
"""

from __future__ import annotations

import argparse
import json
import math
import pathlib
from datetime import datetime

SHIPPED_HALF_LIFE_SEC = 3600.0   # HorizonParams.half_life_sec, unmodified

# Measured in eval/results/mythos5/component_reach.json, frozen detector.
RECOGNITION = [11, 12, 29, 34, 35, 1039]
NORM = [12, 35, 179, 182, 743, 982, 1024]
DISCOUNT = [406, 631, 971]


def parse_ts(s):
    if not s:
        return None
    for fmt in ("%Y-%m-%dT%H:%M:%S.%fZ", "%Y-%m-%dT%H:%M:%SZ",
                "%Y-%m-%dT%H:%M:%S.%f%z", "%Y-%m-%dT%H:%M:%S%z"):
        try:
            return datetime.strptime(s, fmt)
        except ValueError:
            continue
    try:
        return datetime.fromisoformat(s.replace("Z", "+00:00"))
    except ValueError:
        return None


def main() -> int:
    ap = argparse.ArgumentParser()
    ap.add_argument("--jsonl", type=pathlib.Path, required=True)
    ap.add_argument("--out", type=pathlib.Path)
    a = ap.parse_args()

    recs = [json.loads(l) for l in a.jsonl.read_text(encoding="utf-8").splitlines() if l.strip()]
    msgs = sorted([r for r in recs if r.get("record") == "message"],
                  key=lambda r: r.get("index", 0))
    tools = [r for r in msgs if r.get("type") == "ToolMessage"]
    ts = {i: parse_ts(r.get("timestamp")) for i, r in enumerate(tools)}

    have = [i for i, t in ts.items() if t is not None]
    if not have:
        print("no parseable timestamps; cannot measure")
        return 1

    t0, tN = ts[min(have)], ts[max(have)]
    span_h = (tN - t0).total_seconds() / 3600.0
    print(f"steps with timestamps : {len(have)} of {len(tools)}")
    print(f"trajectory wall-clock : {span_h:.2f} hours "
          f"({(tN - t0).total_seconds():.0f}s)")
    print(f"shipped half-life     : {SHIPPED_HALF_LIFE_SEC:.0f}s "
          f"({SHIPPED_HALF_LIFE_SEC/3600:.2f}h)\n")

    rows = []
    print("EVERY recognition -> discount pair, and what the shipped decay leaves:")
    for r in RECOGNITION:
        for d in DISCOUNT:
            if ts.get(r) is None or ts.get(d) is None:
                continue
            dt = (ts[d] - ts[r]).total_seconds()
            if dt < 0:
                continue                      # discount precedes recognition
            surviving = math.pow(0.5, dt / SHIPPED_HALF_LIFE_SEC)
            rows.append({"recognition_step": r, "discount_step": d,
                         "delta_sec": dt, "delta_hours": dt / 3600.0,
                         "surviving_fraction": surviving})
            print(f"  step {r:5d} -> {d:5d}   {dt/3600:7.2f} h   "
                  f"evidence surviving: {surviving:.3e}")

    if rows:
        best = max(rows, key=lambda x: x["surviving_fraction"])
        print(f"\nBEST CASE (closest pair in time): step "
              f"{best['recognition_step']} -> {best['discount_step']}, "
              f"{best['delta_hours']:.2f} h apart, "
              f"{best['surviving_fraction']:.3e} of the evidence surviving.")
        halves = best["delta_sec"] / SHIPPED_HALF_LIFE_SEC
        print(f"That is {halves:.1f} half-lives.")

    out = {
        "_what_this_is": "Measurement only. No detector run, no verdict changed.",
        "shipped_half_life_sec": SHIPPED_HALF_LIFE_SEC,
        "trajectory_hours": span_h,
        "pairs": rows,
    }
    if a.out:
        a.out.parent.mkdir(parents=True, exist_ok=True)
        a.out.write_text(json.dumps(out, indent=1), encoding="utf-8")
        print(f"\nwrote {a.out}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
