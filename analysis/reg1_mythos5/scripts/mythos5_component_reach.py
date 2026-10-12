# Published copy (2026-10-13): paths made repo-relative; logic unchanged.
"""Measure each frozen pattern family INDEPENDENTLY, without the conjunctive floor.

WHY THIS EXISTS
---------------
`analyze_step` short-circuits: if `recognition <= 0.0` it returns before norm and
discount are ever computed. So the scored result "discount fired on 0 steps" does
NOT mean the discount patterns match nothing in the transcript -- it means they
were only EVALUATED on the 6 steps where recognition fired.

Reporting that as "the discount component never fired in 1,361 steps" overstates
what was measured, and this script exists to replace the overstatement with the
actual number. It re-runs each pattern family over every step's thought with no
floor, so the question becomes: which arm is the binding constraint?

If discount matches widely and recognition does not, the binding constraint is
the RECOGNITION list and the conjunctive floor, not the discount vocabulary --
which is a materially different diagnosis and a different repair.

This changes NO verdict. The pre-registered test failed and stays failed; the
detector is not patched. This only makes the post-mortem accurate.

Canary: statistics only, no transcript text.
"""

from __future__ import annotations

import argparse
import json
import pathlib
import sys

HERE = pathlib.Path(__file__).resolve().parent
BACKEND = HERE.parent
if str(BACKEND) not in sys.path:
    sys.path.insert(0, str(BACKEND))

FROZEN = HERE.parents[2] / "detector" / "engine" / "ring12"


def load_frozen():
    """Import the FROZEN registered detector, not the shipped one."""
    sys.path.insert(0, str(FROZEN.parent.parent))
    import importlib
    mod = importlib.import_module("engine.ring12.rationalization")
    return mod


def main() -> int:
    ap = argparse.ArgumentParser()
    ap.add_argument("--steps", type=pathlib.Path, required=True)
    ap.add_argument("--out", type=pathlib.Path)
    a = ap.parse_args()

    rat = load_frozen()
    steps = json.loads(a.steps.read_text(encoding="utf-8"))

    families = {
        "recognition": rat._REALITY_RECOGNITION_PATTERNS,
        "norm": rat._NORM_STATEMENT_PATTERNS,
        "discount": rat._REALITY_DISCOUNT_PATTERNS,
    }

    per_family = {}
    per_pattern = {}
    for name, pats in families.items():
        hit_steps = set()
        for i, p in enumerate(pats):
            s = [st["index"] for st in steps if st["thought"] and p.search(st["thought"])]
            per_pattern[f"{name}[{i}]"] = {"n_steps": len(s), "first": s[0] if s else None,
                                           "pattern": p.pattern[:110]}
            hit_steps.update(s)
        per_family[name] = sorted(hit_steps)

    nonempty = [s["index"] for s in steps if s["thought"].strip()]
    rec, nrm, dis = (set(per_family["recognition"]), set(per_family["norm"]),
                     set(per_family["discount"]))

    print(f"steps: {len(steps)}   with any thought: {len(nonempty)}\n")
    print("INDEPENDENT REACH OF EACH FAMILY (no conjunctive floor):")
    for k in ("recognition", "norm", "discount"):
        v = per_family[k]
        print(f"  {k:12s} {len(v):5d} steps  ({100*len(v)/len(nonempty):5.2f}% of steps with thought)")

    print("\nCONJUNCTIONS:")
    print(f"  recognition AND norm                 {len(rec & nrm):5d}  {sorted(rec & nrm)[:12]}")
    print(f"  recognition AND discount             {len(rec & dis):5d}  {sorted(rec & dis)[:12]}")
    print(f"  norm AND discount                    {len(nrm & dis):5d}  {sorted(nrm & dis)[:12]}")
    print(f"  ALL THREE                            {len(rec & nrm & dis):5d}  {sorted(rec & nrm & dis)[:12]}")
    print(f"\n  discount WITHOUT recognition (invisible to the floor) "
          f"{len(dis - rec):5d}")

    print("\nPER-PATTERN REACH (which individual regexes are dead on this corpus):")
    for k, v in per_pattern.items():
        flag = "DEAD" if v["n_steps"] == 0 else "    "
        print(f"  [{flag}] {k:16s} {v['n_steps']:5d} steps  first@{v['first']}")

    out = {
        "_what_this_is": "Independent per-family reach, floor removed. The "
                         "pre-registered verdict is unchanged and still FAIL.",
        "n_steps": len(steps), "n_steps_with_thought": len(nonempty),
        "family_reach": {k: len(v) for k, v in per_family.items()},
        "family_steps": per_family,
        "conjunctions": {
            "recognition_and_norm": sorted(rec & nrm),
            "recognition_and_discount": sorted(rec & dis),
            "norm_and_discount": sorted(nrm & dis),
            "all_three": sorted(rec & nrm & dis),
            "discount_without_recognition": len(dis - rec),
        },
        "per_pattern": per_pattern,
    }
    if a.out:
        a.out.parent.mkdir(parents=True, exist_ok=True)
        a.out.write_text(json.dumps(out, indent=1), encoding="utf-8")
        print(f"\nwrote {a.out}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
