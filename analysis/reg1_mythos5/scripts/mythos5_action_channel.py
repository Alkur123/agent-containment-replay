# Published copy (2026-10-13): paths made repo-relative; logic unchanged.
"""Is the licence visible in the ACTION channel, or only in reasoning?

WHY
---
Review point: our detector reads chain-of-thought only. A monitor that also
observes actions might reconstruct the same licence without a wide window, which
would make "widen W" the wrong recommendation. That is a testable claim on this
trajectory, not only future work, so it is tested here.

Three channels over the same 1,361 steps:

  REASONING  assistant text attached to the first following action (frozen
             mapping A, exactly what the registered detector scored)
  ACTION     tool name + the arguments the model chose, and separately the
             tool result the environment returned
  COMBINED   both concatenated per step, i.e. the best case for an
             action-aware step-local monitor

For each we report per-family reach, single-unit co-occurrence, and the minimum
enclosing window. If COMBINED collapses the window, the paper's recommendation is
wrong and must say so.

OFF-LABEL USE, STATED UP FRONT
------------------------------
The three pattern families were authored to match reasoning PROSE. Running them
over tool arguments and command output is off-label: a null on the action channel
is weak evidence, because the vocabulary was never built to match that register.
A POSITIVE on the action channel is strong evidence, because it needs no
assumption about coverage. So this measurement can refute the paper's
recommendation but cannot confirm it, and it is read only in that direction.

Canary: statistics only.
"""

from __future__ import annotations

import argparse
import json
import pathlib
import sys

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


def flatten(v) -> str:
    """Tool arguments are nested; render every leaf string."""
    if v is None:
        return ""
    if isinstance(v, str):
        return v
    if isinstance(v, dict):
        return " ".join(flatten(x) for x in v.values())
    if isinstance(v, (list, tuple)):
        return " ".join(flatten(x) for x in v)
    return str(v)


def hits_for(units):
    return {name: sorted(i for i, t in enumerate(units)
                         if t and any(p.search(t) for p in pats))
            for name, pats in FAMILIES.items()}


def min_enclosing_window(hits):
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


def build_channels(recs):
    msgs = sorted([r for r in recs if r.get("record") == "message"],
                  key=lambda r: r.get("index", 0))
    reasoning, action, result, pending = [], [], [], []
    for r in msgs:
        if r.get("type") == "TextMessage":
            if r.get("role") == "Assistant" and r.get("content"):
                pending.append(r["content"])
        elif r.get("type") == "ToolMessage":
            reasoning.append("\n".join(pending))
            pending = []
            action.append((r.get("tool_name") or "") + " "
                          + flatten(r.get("tool_call")))
            result.append(flatten(r.get("tool_result")))
    combined = [" ".join(x) for x in zip(reasoning, action, result)]
    return {"reasoning_only_FROZEN": reasoning,
            "action_only": action,
            "tool_result_only": result,
            "combined_all_three": combined}


def main() -> int:
    ap = argparse.ArgumentParser()
    ap.add_argument("--jsonl", type=pathlib.Path, required=True)
    ap.add_argument("--out", type=pathlib.Path)
    a = ap.parse_args()

    recs = [json.loads(l) for l in
            a.jsonl.read_text(encoding="utf-8").splitlines() if l.strip()]
    chans = build_channels(recs)

    print("=" * 74)
    print("DOES AN ACTION-AWARE MONITOR COLLAPSE THE WINDOW?")
    print("=" * 74)
    print("(off-label: the vocabulary was authored for reasoning prose;")
    print(" a null here is weak, a positive would be decisive)\n")

    out = {}
    for name, units in chans.items():
        h = hits_for(units)
        m = min_enclosing_window(h)
        out[name] = {
            "n_units": len(units),
            "units_with_text": sum(1 for u in units if u and u.strip()),
            "total_words": sum(len(u.split()) for u in units),
            "reach": {k: len(v) for k, v in h.items()},
            "co_occur_in_one_unit": sum(1 for i in range(len(units))
                                        if all(i in h[f] for f in FAMILIES)),
            "min_enclosing_window_steps": None if m is None else m[0],
        }
        print(f"  {name}")
        print(f"    words {out[name]['total_words']:>8}   "
              f"reach {out[name]['reach']}")
        print(f"    all three in ONE step : {out[name]['co_occur_in_one_unit']}")
        print(f"    min enclosing window  : "
              f"{out[name]['min_enclosing_window_steps']}\n")

    base = out["reasoning_only_FROZEN"]["min_enclosing_window_steps"]
    comb = out["combined_all_three"]["min_enclosing_window_steps"]
    if comb is not None and base is not None and comb < base:
        verdict = ("REFUTED: an action-aware step-local monitor narrows the "
                   f"window {base} -> {comb}. The paper's recommendation must "
                   "be qualified.")
    elif comb == base:
        verdict = ("NOT REFUTED: adding both action channels leaves the "
                   f"minimum enclosing window at {base} steps. Consistent with "
                   "the paper's recommendation; not confirmation of it, for "
                   "the off-label reason above.")
    else:
        verdict = "INCONCLUSIVE: combined channel has no enclosing window."
    print("  " + verdict)

    doc = {"_what_this_is": "Per-channel family reach and minimum enclosing "
                            "window, testing whether an action-aware step-local "
                            "monitor would see what a CoT-only one missed.",
           "_direction_of_evidence": "A positive on a non-reasoning channel "
                                     "refutes; a null is weak because the "
                                     "vocabulary is off-label there.",
           "verdict": verdict,
           "channels": out}
    if a.out:
        a.out.parent.mkdir(parents=True, exist_ok=True)
        a.out.write_text(json.dumps(doc, indent=1), encoding="utf-8")
        print(f"\nwrote {a.out}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
