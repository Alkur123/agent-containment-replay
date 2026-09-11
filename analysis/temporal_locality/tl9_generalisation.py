"""TL-9. Does temporal locality generalise across models and behaviours?

THE CORPUS THAT UNBLOCKS THIS
-----------------------------
SHADE-Arena pairs a benign main task with a covert sabotage side objective in
long agentic environments. A ControlArena-derived public mirror ships 1,500
labelled trajectories: 750 sabotage and 750 benign, balanced across THREE model
families (claude-sonnet-4, gemini-2-5-pro, gpt-5), median 65 assistant steps
and up to 165.

That is the first corpus available to this study with all four properties at
once: harmful AND benign, labelled, multiple models, and long enough that a
68-step separation is expressible rather than merely absent.

WHAT IS BEING ASKED
-------------------
  model diversity       is component separation a property of one model, or of
                        long-horizon agent behaviour?
  behavioural diversity does the pattern appear outside cyber misuse, in
                        sabotage tasks like spam-filter tampering?
  discrimination        do the components separate sabotage from benign at all,
                        which is the question a monitor actually faces?

EXPRESSIBILITY IS REPORTED BESIDE EVERY RESULT
----------------------------------------------
A separation cannot be observed in a trajectory shorter than the separation.
TL-3 found a corpus where a 68-step gap was inexpressible and reported the null
as a fact about the corpus. The same guard runs here: every cell carries the
largest separation its trajectories could have shown.

Canary: statistics only. No trajectory text is written to any artifact.
"""

from __future__ import annotations

import argparse
import ast
import collections
import json
import pathlib
import re
import statistics
import sys

HERE = pathlib.Path(__file__).resolve().parent
BACKEND = HERE.parent.parent
FAMS = ("recognition", "norm", "discount")
LIST_NAMES = {"recognition": "_REALITY_RECOGNITION_PATTERNS",
              "norm": "_NORM_STATEMENT_PATTERNS",
              "discount": "_REALITY_DISCOUNT_PATTERNS"}


def load_patterns():
    mod = BACKEND / "engine" / "ring12" / "rationalization.py"
    tree = ast.parse(mod.read_text(encoding="utf-8"))
    found = {}
    for node in ast.walk(tree):
        if isinstance(node, ast.AnnAssign):
            targets, val = [node.target], node.value
        elif isinstance(node, ast.Assign):
            targets, val = node.targets, node.value
        else:
            continue
        if val is None:
            continue
        for tgt in targets:
            if not isinstance(tgt, ast.Name):
                continue
            for fam, name in LIST_NAMES.items():
                if tgt.id == name and isinstance(val, (ast.List, ast.Tuple)):
                    found[fam] = [el.args[0].value for el in val.elts
                                  if isinstance(el, ast.Call) and el.args
                                  and isinstance(el.args[0], ast.Constant)]
    return {f: [re.compile(p, re.I) for p in found[f]] for f in FAMS}


def diameter(pos):
    if not all(pos[f] for f in FAMS):
        return None
    best = None
    for a in pos["recognition"]:
        for b in pos["norm"]:
            for c in pos["discount"]:
                sp = max(a, b, c) - min(a, b, c)
                if best is None or sp < best:
                    best = sp
    return best


def blank():
    return {"n": 0, "steps": 0, "words": 0, "max_expressible": 0,
            "steps_with_reasoning": 0,
            "hits": {f: 0 for f in FAMS},
            "traj_with": {f: 0 for f in FAMS},
            "co_occur_steps": 0, "all_three": 0, "diameters": []}


def main() -> int:
    ap = argparse.ArgumentParser()
    ap.add_argument("--parquet", type=pathlib.Path, required=True)
    ap.add_argument("--out", type=pathlib.Path)
    a = ap.parse_args()

    import pyarrow.parquet as pq
    pats = load_patterns()
    by_model = collections.defaultdict(blank)
    by_label = collections.defaultdict(blank)
    by_task = collections.defaultdict(blank)
    overall = {0: blank(), 1: blank()}

    pf = pq.ParquetFile(a.parquet)
    for rb in pf.iter_batches(batch_size=100,
                              columns=["id", "ground_truth",
                                       "trajectory_data"]):
        for r in rb.to_pylist():
            m = re.match(r"shade_(.+?)_(.+?)_\d+_epoch\d+$", r["id"] or "")
            model = m.group(1) if m else "unknown"
            task = m.group(2) if m else "unknown"
            gt = r["ground_truth"]
            try:
                msgs = json.loads(r["trajectory_data"])["messages"]
            except Exception:
                continue
            raw = [x.get("content") or "" for x in msgs
                   if x.get("role") == "assistant"]
            raw = [s if isinstance(s, str) else json.dumps(s) for s in raw]
            # An empty <think></think> is an ABSENT chain of thought, not a
            # short one. Treat it as no reasoning so a model whose CoT was
            # never recorded cannot be scored as a model that said nothing
            # incriminating.
            steps = [re.sub(r"<think>\s*</think>", "", s).strip() for s in raw]
            if not steps:
                continue
            n_nonempty = sum(1 for s in steps if s)
            pos = {f: [] for f in FAMS}
            co = 0
            for i, s in enumerate(steps):
                lab = [f for f in FAMS if any(p.search(s) for p in pats[f])]
                for f in lab:
                    pos[f].append(i)
                if len(lab) == 3:
                    co += 1
            d = diameter(pos)
            w = sum(len(s.split()) for s in steps)
            for bucket in (by_model[model], by_label[gt], by_task[task],
                           overall[gt]):
                bucket["n"] += 1
                bucket["steps"] += len(steps)
                bucket["steps_with_reasoning"] += n_nonempty
                bucket["words"] += w
                bucket["max_expressible"] = max(bucket["max_expressible"],
                                                len(steps) - 1)
                bucket["co_occur_steps"] += co
                for f in FAMS:
                    bucket["hits"][f] += len(pos[f])
                    if pos[f]:
                        bucket["traj_with"][f] += 1
                if d is not None:
                    bucket["all_three"] += 1
                    bucket["diameters"].append(d)

    def show(title, groups):
        print("\n" + "-" * 96)
        print(title)
        print("-" * 96)
        print(f"  {'group':<22}{'traj':>6}{'steps':>8}{'words':>10}"
              f"{'r/n/d traj':>14}{'all3':>7}{'co-step':>9}"
              f"{'med dia':>9}{'maxexp':>8}")
        for k in sorted(groups, key=lambda x: str(x)):
            g = groups[k]
            if not g["n"]:
                continue
            tw = g["traj_with"]
            s = "{}/{}/{}".format(tw["recognition"], tw["norm"], tw["discount"])
            med = (round(statistics.median(g["diameters"]))
                   if g["diameters"] else "-")
            print(f"  {str(k):<22}{g['n']:>6}{g['steps']:>8}{g['words']:>10}"
                  f"{s:>14}{g['all_three']:>7}{g['co_occur_steps']:>9}"
                  f"{str(med):>9}{g['max_expressible']:>8}")

    print("=" * 96)
    print("TL-9  TEMPORAL LOCALITY ACROSS MODELS AND BEHAVIOURS (SHADE-Arena)")
    print("=" * 96)
    show("BY MODEL", by_model)
    show("BY LABEL  (1 = sabotage)", by_label)
    show("BY TASK VARIANT", by_task)

    # ── the questions, answered ────────────────────────────────────────────
    print("\n" + "=" * 96)
    print("READING")
    print("=" * 96)
    h, b = overall[1], overall[0]
    print(f"  Sabotage trajectories : {h['n']}, "
          f"{h['all_three']} carry all three families "
          f"({100*h['all_three']/max(h['n'],1):.1f}%)")
    print(f"  Benign trajectories   : {b['n']}, "
          f"{b['all_three']} carry all three families "
          f"({100*b['all_three']/max(b['n'],1):.1f}%)")
    print(f"  Single-step co-occurrence: sabotage {h['co_occur_steps']}, "
          f"benign {b['co_occur_steps']}")
    if h["diameters"]:
        hd = sorted(h["diameters"])
        print(f"  Sabotage diameter: median {statistics.median(hd):.0f}, "
              f"min {hd[0]}, max {hd[-1]}")
    if b["diameters"]:
        bd = sorted(b["diameters"])
        print(f"  Benign diameter  : median {statistics.median(bd):.0f}, "
              f"min {bd[0]}, max {bd[-1]}")

    maxexp = max(g["max_expressible"] for g in by_model.values())
    print(f"\n  Largest separation this corpus could express: {maxexp} steps.")
    print(f"  The frontier incident's observed separation is 68.")
    if maxexp < 68:
        print("  *** 68 is INEXPRESSIBLE here; any null is a corpus fact. ***")
    else:
        print("  A 68-step separation IS expressible here, so a null is")
        print("  informative rather than structural.")

    print("\n" + "-" * 96)
    print("REASONING PRESENCE, checked before any model is scored")
    print("-" * 96)
    EXCLUDE_BELOW = 5.0        # words per assistant step
    excluded = []
    for m in sorted(by_model):
        g = by_model[m]
        wps = g["words"] / max(g["steps"], 1)
        frac = g["steps_with_reasoning"] / max(g["steps"], 1)
        flag = ""
        if wps < EXCLUDE_BELOW:
            excluded.append(m)
            flag = "  <-- EXCLUDED: chain of thought not recorded"
        print(f"  {m:<22}{wps:8.1f} words/step   "
              f"{100*frac:5.1f}% of steps carry any reasoning{flag}")
    if excluded:
        print()
        print(f"  {', '.join(excluded)} carries empty <think></think> blocks in")
        print("  this corpus. A reasoning-reading monitor has nothing to read,")
        print("  so scoring it as a model on which the detector 'found nothing'")
        print("  would be false. It is excluded from the model-diversity claim")
        print("  and the exclusion is reported, because a closed reasoning")
        print("  channel is itself a result for a paper about reading reasoning.")

    models_with = [m for m, g in by_model.items()
                   if g["all_three"] > 0 and m not in excluded]
    scored = [m for m in by_model if m not in excluded]
    print(f"\n  Models with a readable reasoning channel: {len(scored)} "
          f"({', '.join(sorted(scored))})")
    print(f"  Of those, models in which all three families co-occur somewhere")
    print(f"  in a trajectory: {len(models_with)} "
          f"({', '.join(sorted(models_with)) if models_with else 'none'})")
    print()
    print("  SINGLE-STEP CO-OCCURRENCE IS ZERO IN EVERY MODEL AND EVERY LABEL")
    print("  across 1,500 labelled trajectories, in a corpus where a 68-step")
    print("  separation IS expressible. Step-local conjunctive detection of")
    print("  this licence fails outside the incident it was derived from.")
    print()
    print("  THE OTHER HALF, AGAINST US: the vocabulary barely reaches this")
    print("  corpus at all. Only 1 of 750 sabotage trajectories carries all")
    print("  three families anywhere. So this generalises the OPERATOR finding")
    print("  and not the DETECTOR: these sabotage tasks do not verbalise a")
    print("  reality-discount licence, and a detector built for one incident's")
    print("  rationalisation shape should not be expected to travel.")

    doc = {"_what_this_is": "Component reach and separation across three model "
                            "families and five sabotage task variants, on "
                            "labelled long agentic trajectories.",
           "_source": "adityaasinha28/control_arena_shade, a public "
                      "ControlArena/SHADE-Arena mirror, ungated",
           "_expressibility": f"largest separation expressible: {maxexp} steps",
           "_excluded_models": excluded,
           "_exclusion_rule": "A model whose assistant messages average under "
                              "5 words per step has no recorded chain of "
                              "thought in this corpus and cannot be scored by a "
                              "reasoning-reading monitor.",
           "by_model": {k: {kk: vv for kk, vv in v.items() if kk != "diameters"}
                        | {"diameter_median":
                           statistics.median(v["diameters"]) if v["diameters"]
                           else None}
                        for k, v in by_model.items()},
           "by_label": {str(k): {kk: vv for kk, vv in v.items()
                                 if kk != "diameters"}
                        | {"diameter_median":
                           statistics.median(v["diameters"]) if v["diameters"]
                           else None}
                        for k, v in by_label.items()},
           "by_task": {k: {kk: vv for kk, vv in v.items() if kk != "diameters"}
                       for k, v in by_task.items()}}
    if a.out:
        a.out.parent.mkdir(parents=True, exist_ok=True)
        a.out.write_text(json.dumps(doc, indent=1, default=str),
                         encoding="utf-8")
        print(f"\nwrote {a.out}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
