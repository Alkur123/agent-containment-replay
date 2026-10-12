# Published copy (2026-10-13): paths made repo-relative; logic unchanged.
"""Temporal-window sweep: recall and a benign false-positive bound as functions of W.

WHY
---
The paper's finding is a point claim: a conjunction evaluated within ONE step
cannot see conjuncts separated by 68 steps. A reviewer correctly observes that
the interesting object is the whole curve, because the window W is a
safety-critical design parameter of any conjunctive monitor and not a detail.

So this computes two functions of W over the released trajectory:

  RECALL(W)  does some window of W consecutive steps contain at least one match
             from each of the three families? For n=1 this is a step function,
             and its knee is the minimum enclosing window. That knee is the
             quantity a monitor designer needs and nobody currently reports.

  FPRBOUND(W) at the 95% upper bound the benign corpus can resolve, what is the
             probability that all three families fire at least once inside a
             window of W steps of BENIGN reasoning? Rising in W by construction.

The two together are the tradeoff: widening W is the only way to see distributed
evidence, and it is also the only way to accumulate benign coincidences.

WHAT THIS IS NOT
----------------
n = 1 trajectory. RECALL(W) here is not a recall rate over a population; it is
"was this incident's licence enclosable at window W". Stated that way in the
paper. The FPR bound is an upper bound from zero observations by the rule of
three, not a measured rate.

CONVERSION SENSITIVITY
----------------------
The same reviewer asks whether the separation is a property of the detector or
of our segmentation. So every quantity is recomputed under three mappings of
reasoning text to units, and the minimum enclosing window is reported for each.

Canary: statistics only.
"""

from __future__ import annotations

import argparse
import json
import math
import pathlib
import sys
from datetime import datetime

HERE = pathlib.Path(__file__).resolve().parent
BACKEND = HERE.parents[2] / "detector"   # the frozen public detector
if str(BACKEND) not in sys.path:
    sys.path.insert(0, str(BACKEND))

from engine.ring12.rationalization import (                  # noqa: E402
    _NORM_STATEMENT_PATTERNS, _REALITY_DISCOUNT_PATTERNS,
    _REALITY_RECOGNITION_PATTERNS,
)

FAMILIES = {"recognition": _REALITY_RECOGNITION_PATTERNS,
            "norm": _NORM_STATEMENT_PATTERNS,
            "discount": _REALITY_DISCOUNT_PATTERNS}

WINDOWS = [1, 2, 5, 10, 20, 50, 68, 100, 200, 400, 700, 1361]
BENIGN_WORDS = 9503          # externally authored benign reasoning available
BENIGN_UB_PER_WORD = 3.0 / BENIGN_WORDS   # rule of three, 95% upper bound


def parse_ts(s):
    if not s:
        return None
    for f in ("%Y-%m-%dT%H:%M:%S.%fZ", "%Y-%m-%dT%H:%M:%SZ"):
        try:
            return datetime.strptime(s, f)
        except ValueError:
            pass
    try:
        return datetime.fromisoformat(s.replace("Z", "+00:00"))
    except ValueError:
        return None


def hits_for(units):
    """{family: sorted unit indices where it matches}."""
    out = {}
    for name, pats in FAMILIES.items():
        out[name] = sorted(i for i, t in enumerate(units)
                           if t and any(p.search(t) for p in pats))
    return out


def min_enclosing_window(hits):
    """Smallest span containing >=1 match from each family, in unit indices."""
    r, n, d = hits["recognition"], hits["norm"], hits["discount"]
    if not (r and n and d):
        return None
    best = None
    for a in r:
        for b in n:
            for c in d:
                span = max(a, b, c) - min(a, b, c)
                if best is None or span < best[0]:
                    best = (span, a, b, c)
    return best


def recall_at(hits, w, n_units):
    """Does any window of w consecutive units enclose all three families?"""
    m = min_enclosing_window(hits)
    return (m is not None) and (m[0] <= w - 1)


def fpr_bound_at(w, words_per_unit):
    """P(all three families fire >=1 in w benign units) at the rule-of-three
    upper bound. Independence across families is assumed, which is the
    optimistic direction for the monitor and is stated as such."""
    words = w * words_per_unit
    per_family = 1.0 - math.pow(1.0 - BENIGN_UB_PER_WORD, words)
    return per_family ** 3


# ── mappings of reasoning text to units ──────────────────────────────────────
def build_mappings(recs):
    msgs = sorted([r for r in recs if r.get("record") == "message"],
                  key=lambda r: r.get("index", 0))
    # A: reasoning attaches to the FIRST following action (the frozen spec)
    a_units, pending = [], []
    # B: reasoning attaches to EVERY action until the next reasoning block
    b_units, cur = [], ""
    # D: reasoning blocks are the units; actions are not units at all
    d_units = []
    ts = []
    for r in msgs:
        if r.get("type") == "TextMessage":
            if r.get("role") == "Assistant" and r.get("content"):
                pending.append(r["content"])
                cur = r["content"]
                d_units.append(r["content"])
        elif r.get("type") == "ToolMessage":
            a_units.append("\n".join(pending))
            pending = []
            b_units.append(cur)
            ts.append(parse_ts(r.get("timestamp")))
    # C: explicit TEMPORAL segments. Units are fixed wall-clock buckets, so the
    # unit boundary owes nothing to how the transcript numbers its actions.
    # This is the mapping that most directly answers "is the separation ours?",
    # because it discards the step index entirely.
    c_units = []
    base = next((t for t in ts if t), None)
    if base is not None:
        bucket_secs = 300.0                       # 5 minutes
        span = max((t for t in ts if t), default=base)
        n_buckets = int(((span - base).total_seconds()) // bucket_secs) + 1
        c_units = [""] * n_buckets
        for u, t in zip(a_units, ts):
            if t is None or not u:
                continue
            b = int((t - base).total_seconds() // bucket_secs)
            c_units[b] = (c_units[b] + "\n" + u) if c_units[b] else u

    return {"A_first_action": a_units,
            "B_all_actions_until_next": b_units,
            "C_temporal_segments_5min": c_units,
            "D_reasoning_blocks": d_units}, ts


def main() -> int:
    ap = argparse.ArgumentParser()
    ap.add_argument("--jsonl", type=pathlib.Path, required=True)
    ap.add_argument("--out", type=pathlib.Path)
    a = ap.parse_args()

    recs = [json.loads(l) for l in a.jsonl.read_text(encoding="utf-8").splitlines()
            if l.strip()]
    mappings, ts = build_mappings(recs)

    print("=" * 74)
    print("CONVERSION SENSITIVITY: does the separation survive the segmentation?")
    print("=" * 74)
    sens = {}
    for name, units in mappings.items():
        h = hits_for(units)
        m = min_enclosing_window(h)
        nonempty = sum(1 for u in units if u and u.strip())
        sens[name] = {
            "n_units": len(units), "units_with_text": nonempty,
            "reach": {k: len(v) for k, v in h.items()},
            "co_occur_in_one_unit": sum(
                1 for i in range(len(units))
                if all(i in h[f] for f in FAMILIES)),
            "min_enclosing_window_units": None if m is None else m[0],
        }
        print(f"\n  {name}")
        print(f"    units {len(units)}, with text {nonempty}")
        print(f"    reach {sens[name]['reach']}")
        print(f"    all three in ONE unit : {sens[name]['co_occur_in_one_unit']}")
        print(f"    min enclosing window  : {sens[name]['min_enclosing_window_units']} units")

    # ── the sweep, on the frozen mapping ────────────────────────────────────
    units = mappings["A_first_action"]
    h = hits_for(units)
    nonempty = [i for i, u in enumerate(units) if u and u.strip()]
    total_words = sum(len(u.split()) for u in units)
    wpu = total_words / max(len(nonempty), 1)

    print("\n" + "=" * 74)
    print("TEMPORAL WINDOW SWEEP (frozen mapping A)")
    print("=" * 74)
    print(f"words per reasoning-bearing unit: {wpu:.1f}")
    print(f"benign 95% upper bound per word : {BENIGN_UB_PER_WORD:.3e}\n")
    print(f"  {'W (steps)':>10}  {'encloses licence':>17}  {'benign FP bound':>16}")
    rows = []
    for w in WINDOWS:
        rec = recall_at(h, w, len(units))
        fp = fpr_bound_at(w, wpu)
        rows.append({"window_steps": w, "encloses_licence": rec,
                     "benign_fp_upper_bound": fp})
        print(f"  {w:10d}  {str(rec):>17}  {100*fp:15.2f}%")

    m = min_enclosing_window(h)
    knee_secs = None
    if m and ts and m[1] < len(ts) and m[3] < len(ts):
        lo, hi = min(m[1], m[2], m[3]), max(m[1], m[2], m[3])
        if ts[lo] and ts[hi]:
            knee_secs = (ts[hi] - ts[lo]).total_seconds()

    print(f"\n  KNEE: minimum enclosing window = {m[0]} steps"
          + (f", {knee_secs/3600:.2f} wall-clock hours" if knee_secs else ""))
    print(f"  at that window the benign false-positive UPPER BOUND is "
          f"{100*fpr_bound_at(m[0]+1, wpu):.2f}%")

    doc = {"_what_this_is": "Recall and a benign FP upper bound as functions of "
                            "the temporal window W, plus conversion sensitivity. "
                            "n=1 trajectory: 'encloses_licence' is not a "
                            "population recall rate.",
           "benign_words": BENIGN_WORDS,
           "benign_upper_bound_per_word": BENIGN_UB_PER_WORD,
           "words_per_unit": wpu,
           "min_enclosing_window_steps": m[0] if m else None,
           "min_enclosing_window_seconds": knee_secs,
           "sweep": rows,
           "conversion_sensitivity": sens}
    if a.out:
        a.out.parent.mkdir(parents=True, exist_ok=True)
        a.out.write_text(json.dumps(doc, indent=1), encoding="utf-8")
        print(f"\nwrote {a.out}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
