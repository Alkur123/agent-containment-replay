"""TL-3. Behavioural diversity, and an honest benign hit rate with a control.

TWO QUESTIONS, ONE CORPUS
-------------------------
The external SLEIGHT-Bench ships 44 attack trajectories across 11 behaviour
families, each with a paired benign counterpart. That answers two rows of the
programme that the single frontier incident cannot:

  behavioural diversity  does component evidence appear, and appear separated,
                         across behaviour families other than cyber misuse?
  benign coincidence     how often do the families fire on real benign agent
                         reasoning, with a denominator worth quoting?

WHY A POSITIVE CONTROL IS MANDATORY HERE
----------------------------------------
A benign rate of zero and a broken matcher look identical. This project has
already published one number that turned out to be a short-circuit rather than
a measurement. So every run scores the three incident blocks too: if the
control does not fire, the run is void and says so.

WHAT THIS CORPUS CANNOT DO, STATED BEFORE THE NUMBERS
-----------------------------------------------------
These trajectories are SHORT. If the mean reasoning-bearing length is on the
order of a handful of steps, then a separation of 68 steps is not merely absent
but inexpressible, and any "no separation observed" result is a statement about
the corpus, not about the behaviour. The script computes the longest separation
each family could possibly express and reports it beside every result.

Canary: statistics only. No corpus text is written to any artifact.
"""

from __future__ import annotations

import argparse
import collections
import json
import pathlib
import sys

HERE = pathlib.Path(__file__).resolve().parent
BACKEND = HERE.parent.parent
if str(BACKEND) not in sys.path:
    sys.path.insert(0, str(BACKEND))

from engine.ring12.rationalization import (                  # noqa: E402
    _NORM_STATEMENT_PATTERNS, _REALITY_DISCOUNT_PATTERNS,
    _REALITY_RECOGNITION_PATTERNS,
)

FAMS = ("recognition", "norm", "discount")
PATS = {"recognition": _REALITY_RECOGNITION_PATTERNS,
        "norm": _NORM_STATEMENT_PATTERNS,
        "discount": _REALITY_DISCOUNT_PATTERNS}


def label(text):
    return frozenset(f for f in FAMS
                     if text and any(p.search(text) for p in PATS[f]))


def reasoning_steps(path: pathlib.Path):
    """Assistant free-text messages, in order: the channel the detector reads."""
    out = []
    for line in path.read_text(encoding="utf-8", errors="replace").splitlines():
        if not line.strip():
            continue
        try:
            r = json.loads(line)
        except Exception:
            continue
        if r.get("role") != "assistant":
            continue
        c = r.get("content")
        if isinstance(c, dict) and c.get("type") == "text":
            out.append(str(c.get("text", "")))
    return out


def diameter(labels):
    pos = {f: [i for i, l in enumerate(labels) if f in l] for f in FAMS}
    if not all(pos[f] for f in FAMS):
        return None, pos
    best = None
    for a in pos["recognition"]:
        for b in pos["norm"]:
            for c in pos["discount"]:
                span = max(a, b, c) - min(a, b, c)
                if best is None or span < best:
                    best = span
    return best, pos


def incident_control(path: pathlib.Path):
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
    return {f: sum(1 for u in units if f in label(u)) for f in FAMS}


def scan(files):
    per_fam = collections.defaultdict(lambda: {
        "trajectories": 0, "steps": 0, "words": 0,
        "hits": {f: 0 for f in FAMS},
        "traj_with_all_three": 0, "diameters": [],
        "max_expressible": 0})
    for p in files:
        fam = p.parent.parent.name
        texts = reasoning_steps(p)
        labs = [label(t) for t in texts]
        d = per_fam[fam]
        d["trajectories"] += 1
        d["steps"] += len(texts)
        d["words"] += sum(len(t.split()) for t in texts)
        d["max_expressible"] = max(d["max_expressible"], max(0, len(texts) - 1))
        for l in labs:
            for f in l:
                d["hits"][f] += 1
        dia, _ = diameter(labs)
        if dia is not None:
            d["traj_with_all_three"] += 1
            d["diameters"].append(dia)
    return per_fam


def main() -> int:
    ap = argparse.ArgumentParser()
    ap.add_argument("--sleight", type=pathlib.Path, required=True)
    ap.add_argument("--incident", type=pathlib.Path, required=True)
    ap.add_argument("--out", type=pathlib.Path)
    a = ap.parse_args()

    ctrl = incident_control(a.incident)
    print("=" * 78)
    print("TL-3  BEHAVIOURAL DIVERSITY + BENIGN HIT RATE")
    print("=" * 78)
    print(f"  POSITIVE CONTROL (frontier incident): {ctrl}")
    if not all(ctrl[f] > 0 for f in FAMS):
        print("  CONTROL FAILED: matcher is not live. Run is VOID.")
        return 1
    print("  control fires on all three families: matcher is live.\n")

    atk = scan(sorted(a.sleight.rglob("transcript.jsonl")))
    ben = scan(sorted(a.sleight.rglob("benign.jsonl")))

    def report(title, per_fam):
        print("-" * 78)
        print(title)
        print("-" * 78)
        print(f"  {'family':<30}{'traj':>5}{'steps':>7}{'words':>8}"
              f"{'r/n/d hits':>14}{'all3':>6}{'maxsep':>8}")
        tot = {"traj": 0, "steps": 0, "words": 0,
               "hits": {f: 0 for f in FAMS}, "all3": 0, "dia": []}
        for fam in sorted(per_fam):
            d = per_fam[fam]
            h = d["hits"]
            hs = "{}/{}/{}".format(h["recognition"], h["norm"], h["discount"])
            print(f"  {fam:<30}{d['trajectories']:>5}{d['steps']:>7}"
                  f"{d['words']:>8}{hs:>14}"
                  f"{d['traj_with_all_three']:>6}{d['max_expressible']:>8}")
            tot["traj"] += d["trajectories"]
            tot["steps"] += d["steps"]
            tot["words"] += d["words"]
            tot["all3"] += d["traj_with_all_three"]
            tot["dia"] += d["diameters"]
            for f in FAMS:
                tot["hits"][f] += h[f]
        h = tot["hits"]
        hs = "{}/{}/{}".format(h["recognition"], h["norm"], h["discount"])
        print(f"  {'TOTAL':<30}{tot['traj']:>5}{tot['steps']:>7}"
              f"{tot['words']:>8}{hs:>14}{tot['all3']:>6}")
        return tot

    ta = report("ATTACK trajectories, by behaviour family", atk)
    print()
    tb = report("BENIGN counterparts", ben)

    print("\n" + "=" * 78)
    print("READING")
    print("=" * 78)
    mean_len = ta["steps"] / max(ta["traj"], 1)
    print(f"  Mean reasoning-bearing length of an attack trajectory: "
          f"{mean_len:.1f} steps.")
    print(f"  The frontier incident's observed diameter is 68 steps.")
    if mean_len < 68:
        print(f"  *** A 68-step separation is INEXPRESSIBLE in this corpus. ***")
        print(f"  The longest separation any trajectory here could show is "
              f"{max((d['max_expressible'] for d in atk.values()), default=0)} "
              f"steps.")
        print("  So this corpus can say whether the COMPONENTS appear across")
        print("  behaviour families. It cannot say whether they SEPARATE,")
        print("  because it is too short to express the separation. That is a")
        print("  property of the available corpora, not of the behaviours, and")
        print("  it is the same wall the benign side of this programme hits.")
    hb = tb["hits"]
    print(f"\n  Benign reasoning: {tb['words']:,} words, "
          f"hits r/n/d = {hb['recognition']}/{hb['norm']}/{hb['discount']}, "
          f"{tb['all3']} of {tb['traj']} trajectories with all three.")
    if sum(hb.values()) == 0:
        print("  Zero benign hits. With the control passing above, this is a")
        print("  measurement and not a broken matcher; but the corpus is small,")
        print("  so it bounds the rate rather than estimating it.")

    doc = {"_what_this_is": "Component reach and separation across 11 external "
                            "behaviour families, plus the benign hit rate on "
                            "their paired counterparts.",
           "_control": ctrl,
           "_control_passed": all(ctrl[f] > 0 for f in FAMS),
           "_corpus_limit": "Mean attack trajectory is "
                            f"{mean_len:.1f} reasoning steps; a 68-step "
                            "separation is not expressible here.",
           "attack": {k: {kk: vv for kk, vv in v.items()} for k, v in atk.items()},
           "benign": {k: {kk: vv for kk, vv in v.items()} for k, v in ben.items()},
           "attack_totals": ta, "benign_totals": tb}
    if a.out:
        a.out.parent.mkdir(parents=True, exist_ok=True)
        a.out.write_text(json.dumps(doc, indent=1, default=list),
                         encoding="utf-8")
        print(f"\nwrote {a.out}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
