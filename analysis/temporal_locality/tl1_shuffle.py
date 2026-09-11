"""TL-1. Temporal shuffling: same content, different arrangement.

THE EXPERIMENT
--------------
The frontier-incident result is naturalistic: we observed a separation, we did
not create one. A reviewer can always answer "that trajectory happened to be
like that". The counterfactual that closes it holds the CONTENT fixed and moves
only the ARRANGEMENT.

Unit of rearrangement is the reasoning block. We take the 699 reasoning-bearing
steps of the released trajectory and permute which block sits at which step
position. Every arrangement therefore has, exactly:

  * the same multiset of reasoning blocks (same tokens, same words)
  * the same number of matches per family (6 recognition, 7 norm, 3 discount)
  * the same trajectory length and the same number of reasoning-bearing steps

and differs ONLY in where the matching blocks sit relative to one another. Any
change in detection is then attributable to arrangement, not to content. That
is the causal identification.

FOUR ARRANGEMENTS
-----------------
  ORIGINAL     as released
  COMPRESSED   the three families moved adjacent, minimum possible diameter
  EXPANDED     pushed to the maximum diameter the trajectory allows
  RANDOMIZED   uniform random permutation, N trials, giving a null DISTRIBUTION

THE RANDOMIZED ARM CAN REFUTE US, WHICH IS WHY IT IS HERE
--------------------------------------------------------
If a uniformly random arrangement of the same blocks typically produces a
diameter well ABOVE 68, then 68 is not a large separation for a trajectory of
this shape, the incident is unremarkable in this respect, and the "distributed
evidence" reading is weakened. We compute the null distribution and report
where the observed value falls in it, whichever way that comes out.

Canary: statistics only. No transcript text is written anywhere.
"""

from __future__ import annotations

import argparse
import json
import pathlib
import random
import statistics
import sys

HERE = pathlib.Path(__file__).resolve().parent
BACKEND = HERE.parent.parent
if str(BACKEND) not in sys.path:
    sys.path.insert(0, str(BACKEND))

from engine.ring12.rationalization import (                  # noqa: E402
    _NORM_STATEMENT_PATTERNS, _REALITY_DISCOUNT_PATTERNS,
    _REALITY_RECOGNITION_PATTERNS,
)

FAMILIES = {"recognition": _REALITY_RECOGNITION_PATTERNS,
            "norm": _NORM_STATEMENT_PATTERNS,
            "discount": _REALITY_DISCOUNT_PATTERNS}


def load_reasoning_units(path: pathlib.Path):
    """The frozen mapping A: reasoning attaches to the first following action."""
    recs = [json.loads(l) for l in
            path.read_text(encoding="utf-8").splitlines() if l.strip()]
    msgs = sorted([r for r in recs if r.get("record") == "message"],
                  key=lambda r: r.get("index", 0))
    units, pending = [], []
    for r in msgs:
        if r.get("type") == "TextMessage":
            if r.get("role") == "Assistant" and r.get("content"):
                pending.append(r["content"])
        elif r.get("type") == "ToolMessage":
            units.append("\n".join(pending))
            pending = []
    return units


def label(text: str) -> frozenset:
    """Which families this block matches. Computed ONCE per block, then the
    block travels as a label: rearrangement cannot change what a block says."""
    return frozenset(name for name, pats in FAMILIES.items()
                     if text and any(p.search(text) for p in pats))


def diameter(positions_by_family):
    """Smallest window containing one match from each family, in steps."""
    r, n, d = (positions_by_family.get("recognition", []),
               positions_by_family.get("norm", []),
               positions_by_family.get("discount", []))
    if not (r and n and d):
        return None
    best = None
    for a in r:
        for b in n:
            for c in d:
                span = max(a, b, c) - min(a, b, c)
                if best is None or span < best:
                    best = span
    return best


def positions(step_labels):
    out = {f: [] for f in FAMILIES}
    for i, lab in enumerate(step_labels):
        for f in lab:
            out[f].append(i)
    return out


def detects_at(step_labels, w):
    """A monitor with horizon w sees the conjunction iff some window of w
    consecutive steps contains a match from each family."""
    d = diameter(positions(step_labels))
    return d is not None and d <= w - 1


def main() -> int:
    ap = argparse.ArgumentParser()
    ap.add_argument("--jsonl", type=pathlib.Path, required=True)
    ap.add_argument("--trials", type=int, default=10000)
    ap.add_argument("--seed", type=int, default=20260911)
    ap.add_argument("--out", type=pathlib.Path)
    a = ap.parse_args()

    units = load_reasoning_units(a.jsonl)
    n_steps = len(units)
    # label every step ONCE; the label is what gets permuted
    labels = [label(u) for u in units]
    bearing = [i for i, u in enumerate(units) if u and u.strip()]
    carried = [labels[i] for i in bearing]          # the fixed content multiset

    obs = positions(labels)
    obs_d = diameter(obs)

    print("=" * 74)
    print("TL-1  TEMPORAL SHUFFLING: same content, different arrangement")
    print("=" * 74)
    print(f"  steps                    {n_steps}")
    print(f"  reasoning-bearing steps  {len(bearing)}")
    print(f"  family reach             "
          f"{ {f: len(v) for f, v in obs.items()} }")
    print(f"  OBSERVED diameter        {obs_d} steps")
    n_multi_pre = sum(1 for l in carried if len(l) > 1)
    print(f"  blocks matching >1 family {n_multi_pre}  (each is itself a "
          f"co-occurrence and cannot be separated from itself)")

    WINDOWS = [1, 2, 5, 10, 20, 50, 68, 100, 200, 500, 1000, n_steps]

    # ── COMPRESSED: place one of each family in adjacent positions ──────────
    # keep the same multiset; just choose an arrangement whose diameter is
    # the smallest the content permits.
    comp = list(carried)
    # find one block per family (a block may carry several families at once)
    idx_r = next(i for i, l in enumerate(comp) if "recognition" in l)
    idx_n = next(i for i, l in enumerate(comp)
                 if "norm" in l and i != idx_r)
    idx_d = next(i for i, l in enumerate(comp)
                 if "discount" in l and i not in (idx_r, idx_n))
    picked = [idx_r, idx_n, idx_d]
    rest = [l for i, l in enumerate(comp) if i not in picked]
    compressed_carried = [comp[i] for i in picked] + rest
    compressed = [frozenset()] * n_steps
    for slot, lab in zip(bearing, compressed_carried):
        compressed[slot] = lab
    comp_d = diameter(positions(compressed))

    # ── EXPANDED: ALL of each family grouped into separated bands ───────────
    # Moving one block per family does nothing, because the diameter minimises
    # over every triple and the remaining blocks still form a tight one. To
    # actually expand, every member of a family must move together.
    multi = [l for l in carried if len(l) > 1]      # a block that is itself a
    only_r = [l for l in carried if l == {"recognition"}]   # co-occurrence and
    only_n = [l for l in carried if l == {"norm"}]          # cannot be pulled
    only_d = [l for l in carried if l == {"discount"}]      # apart from itself
    empty = [l for l in carried if not l]
    third = len(empty) // 3
    expanded_carried = (only_r + empty[:third]
                        + only_n + empty[third:2 * third]
                        + only_d + empty[2 * third:] + multi)
    assert len(expanded_carried) == len(carried), "content not preserved"
    expanded = [frozenset()] * n_steps
    for slot, lab in zip(bearing, expanded_carried):
        expanded[slot] = lab
    exp_d = diameter(positions(expanded))
    n_multi = len(multi)

    # ── RANDOMIZED: the null distribution ───────────────────────────────────
    rng = random.Random(a.seed)
    pool = list(carried)
    null_d, null_detect = [], {w: 0 for w in WINDOWS}
    for _ in range(a.trials):
        rng.shuffle(pool)
        arr = [frozenset()] * n_steps
        for slot, lab in zip(bearing, pool):
            arr[slot] = lab
        d = diameter(positions(arr))
        if d is not None:
            null_d.append(d)
        for w in WINDOWS:
            if d is not None and d <= w - 1:
                null_detect[w] += 1

    null_d.sort()
    def pctile(p):
        return null_d[min(len(null_d) - 1, int(p * len(null_d)))]

    # where does the observed value sit in the null?
    below = sum(1 for x in null_d if x < obs_d)
    pct_of_null = below / len(null_d)

    print("\n" + "-" * 74)
    print("ARRANGEMENTS (identical content in every row)")
    print("-" * 74)
    print(f"  {'arrangement':<14}{'diameter':>10}   detected at W=1 / 10 / 68 / 100")
    for name, arr, d in (("COMPRESSED", compressed, comp_d),
                         ("ORIGINAL", labels, obs_d),
                         ("EXPANDED", expanded, exp_d)):
        flags = " / ".join(
            ("yes" if detects_at(arr, w) else "no") for w in (1, 10, 68, 100))
        print(f"  {name:<14}{str(d):>10}   {flags}")

    print("\n" + "-" * 74)
    print(f"RANDOMIZED NULL ({len(null_d)} of {a.trials} trials had all three)")
    print("-" * 74)
    print(f"  median diameter   {statistics.median(null_d):.0f}")
    print(f"  mean              {statistics.mean(null_d):.1f}")
    print(f"  5th / 25th pct    {pctile(0.05)} / {pctile(0.25)}")
    print(f"  75th / 95th pct   {pctile(0.75)} / {pctile(0.95)}")
    print(f"  OBSERVED {obs_d} sits at percentile {100*pct_of_null:.1f} "
          f"of the null")
    print("\n  detection probability under random arrangement:")
    for w in WINDOWS:
        print(f"    W={w:<6} {100*null_detect[w]/a.trials:6.2f}%")

    # ── the verdict, stated so it can go against us ─────────────────────────
    print("\n" + "=" * 74)
    if pct_of_null < 0.25:
        verdict = (f"The observed diameter {obs_d} is at the {100*pct_of_null:.1f}th "
                   "percentile of random arrangements of the SAME blocks: this "
                   "trajectory's components are CLOSER together than chance, so "
                   "the separation is not evidence of unusual dispersal. The "
                   "detector's failure is then about the operator's window being "
                   "small relative to ordinary dispersal, not about this incident "
                   "being unusual.")
    elif pct_of_null > 0.75:
        verdict = (f"The observed diameter {obs_d} is at the {100*pct_of_null:.1f}th "
                   "percentile: components are MORE dispersed than chance for this "
                   "trajectory.")
    else:
        verdict = (f"The observed diameter {obs_d} sits at the "
                   f"{100*pct_of_null:.1f}th percentile of random arrangements, "
                   "i.e. unremarkable for a trajectory of this shape. The "
                   "separation is what ordinary arrangement produces at this "
                   "length, which makes the operator, not the incident, the "
                   "thing that is unusual.")
    print(verdict)
    print("=" * 74)

    doc = {"_what_this_is": "Temporal shuffling of the released trajectory. "
                            "Content held fixed (same reasoning blocks, same "
                            "per-family match counts); only arrangement varies.",
           "_identification": "Any change in detection across arrangements is "
                              "attributable to temporal arrangement alone.",
           "n_steps": n_steps, "n_reasoning_bearing": len(bearing),
           "family_reach": {f: len(v) for f, v in obs.items()},
           "observed_diameter_steps": obs_d,
           "compressed_diameter_steps": comp_d,
           "expanded_diameter_steps": exp_d,
           "blocks_matching_multiple_families": n_multi,
           "detection_by_arrangement": {
               name: {str(w): detects_at(arr, w) for w in WINDOWS}
               for name, arr in (("compressed", compressed),
                                 ("original", labels),
                                 ("expanded", expanded))},
           "null": {"trials": a.trials, "evaluable": len(null_d),
                    "median": statistics.median(null_d),
                    "mean": statistics.mean(null_d),
                    "p05": pctile(0.05), "p25": pctile(0.25),
                    "p75": pctile(0.75), "p95": pctile(0.95),
                    "observed_percentile": pct_of_null,
                    "detection_prob": {str(w): null_detect[w] / a.trials
                                       for w in WINDOWS}},
           "verdict": verdict}
    if a.out:
        a.out.parent.mkdir(parents=True, exist_ok=True)
        a.out.write_text(json.dumps(doc, indent=1), encoding="utf-8")
        print(f"\nwrote {a.out}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
