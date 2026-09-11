"""TL-6. Independent re-derivation, and a frozen kit for actual replication.

WHAT THIS IS NOT
----------------
This is NOT independent replication. Independent replication means someone who
did not build the thing runs it. That cannot be done by the party that built
it, and nothing in this file changes that. The row in the results table stays
NOT RUN.

WHAT THIS IS
------------
Two weaker but real things that were available and had not been done.

1. IMPLEMENTATION-INDEPENDENT RE-DERIVATION. Every headline number is
   recomputed by code that shares nothing with the original scripts except the
   frozen vocabulary, which must be shared or the test would be meaningless.
   Specifically this file:

     * does NOT import engine.ring12.rationalization. It reads the module as
       TEXT and re-extracts the pattern literals by AST, so none of the
       module's scoring logic runs. That logic is where this project's worst
       error lived: analyze_step short-circuits when recognition is zero, which
       made a component look dead when it had merely never been evaluated.
     * re-implements segmentation from the written specification rather than
       calling the original converter.
     * re-implements the minimum enclosing window with a different algorithm.
       The originals use a triple nested loop; this uses a sorted three-pointer
       sweep. Two algorithms agreeing is evidence the number is a property of
       the data rather than of one loop.

   If any number disagrees, the disagreement is the result and is printed.

2. A REPLICATION KIT MANIFEST. Emits sha256 for every input and every script in
   the programme, so an external party can verify they are running what we ran.
   That does not make replication happen; it removes an excuse for it not to.

Canary: statistics only.
"""

from __future__ import annotations

import argparse
import ast
import hashlib
import json
import pathlib
import re
import sys

HERE = pathlib.Path(__file__).resolve().parent
BACKEND = HERE.parent.parent
FAMS = ("recognition", "norm", "discount")

# The names the frozen module gives its three pattern lists.
LIST_NAMES = {"recognition": "_REALITY_RECOGNITION_PATTERNS",
              "norm": "_NORM_STATEMENT_PATTERNS",
              "discount": "_REALITY_DISCOUNT_PATTERNS"}


def sha256(p: pathlib.Path) -> str:
    return hashlib.sha256(p.read_bytes()).hexdigest()


def extract_patterns(module_path: pathlib.Path):
    """Pull the regex literals out of the frozen module WITHOUT importing it.

    Importing would execute the scoring logic, which is exactly the code whose
    short-circuit produced a wrong published number once already. Parsing the
    source means the vocabulary is shared and nothing else is.
    """
    tree = ast.parse(module_path.read_text(encoding="utf-8"))
    found = {}
    for node in ast.walk(tree):
        # the frozen module ANNOTATES these lists
        # (_NAME: List[re.Pattern] = [...]), which parses to AnnAssign, not
        # Assign. Handling only Assign silently found nothing.
        if isinstance(node, ast.AnnAssign):
            targets = [node.target]
        elif isinstance(node, ast.Assign):
            targets = node.targets
        else:
            continue
        if node.value is None:
            continue
        for tgt in targets:
            if not isinstance(tgt, ast.Name):
                continue
            for fam, name in LIST_NAMES.items():
                if tgt.id != name:
                    continue
                pats = []
                if isinstance(node.value, (ast.List, ast.Tuple)):
                    for el in node.value.elts:
                        # each element is re.compile("...", flags)
                        if (isinstance(el, ast.Call)
                                and isinstance(el.args[0], ast.Constant)):
                            pats.append(el.args[0].value)
                        elif isinstance(el, ast.Constant):
                            pats.append(el.value)
                found[fam] = pats
    return found


def digest_of(patterns) -> str:
    """A digest over the vocabulary, so a reader can confirm the frozen
    artifact is the one being scored."""
    h = hashlib.sha256()
    for fam in FAMS:
        h.update(fam.encode())
        for p in patterns[fam]:
            h.update(p.encode())
    return h.hexdigest()


def segment(jsonl: pathlib.Path):
    """Segmentation re-implemented from the written spec, not by calling the
    original converter: reasoning attaches to the first action that follows."""
    units, pending = [], []
    for line in jsonl.read_text(encoding="utf-8").splitlines():
        if not line.strip():
            continue
        r = json.loads(line)
        if r.get("record") != "message":
            continue
        t = r.get("type")
        if t == "TextMessage" and r.get("role") == "Assistant":
            c = r.get("content")
            if c:
                pending.append(c)
        elif t == "ToolMessage":
            units.append("\n".join(pending))
            pending = []
    return units


def min_window_sweep(pos):
    """Three-pointer sweep over the merged, sorted event list.

    Deliberately a DIFFERENT algorithm from the triple nested loop the original
    scripts use, so agreement is evidence about the data and not about a loop.
    """
    events = []
    for f in FAMS:
        for i in pos[f]:
            events.append((i, f))
    if not all(pos[f] for f in FAMS):
        return None
    events.sort()
    from collections import defaultdict
    count = defaultdict(int)
    have = 0
    best = None
    left = 0
    for right in range(len(events)):
        _, fr = events[right]
        count[fr] += 1
        if count[fr] == 1:
            have += 1
        while have == 3:
            span = events[right][0] - events[left][0]
            if best is None or span < best:
                best = span
            _, fl = events[left]
            count[fl] -= 1
            if count[fl] == 0:
                have -= 1
            left += 1
    return best


def main() -> int:
    ap = argparse.ArgumentParser()
    ap.add_argument("--jsonl", type=pathlib.Path, required=True)
    ap.add_argument("--out", type=pathlib.Path)
    a = ap.parse_args()

    mod = BACKEND / "engine" / "ring12" / "rationalization.py"
    pats_src = extract_patterns(mod)
    missing = [f for f in FAMS if f not in pats_src or not pats_src[f]]
    if missing:
        print(f"could not extract patterns for: {missing}")
        return 1
    compiled = {f: [re.compile(p, re.I) for p in pats_src[f]] for f in FAMS}

    print("=" * 78)
    print("TL-6  INDEPENDENT RE-DERIVATION (no import of the scoring module)")
    print("=" * 78)
    print(f"  frozen module sha256   {sha256(mod)}")
    print(f"  vocabulary digest      {digest_of(pats_src)}")
    print(f"  patterns extracted     "
          f"{ {f: len(pats_src[f]) for f in FAMS} }")

    units = segment(a.jsonl)
    labels = [frozenset(f for f in FAMS
                        if u and any(p.search(u) for p in compiled[f]))
              for u in units]
    pos = {f: [i for i, l in enumerate(labels) if f in l] for f in FAMS}
    reach = {f: len(pos[f]) for f in FAMS}
    co = sum(1 for l in labels if len(l) == 3)
    d = min_window_sweep(pos)
    bearing = sum(1 for u in units if u and u.strip())
    dead = sum(1 for f in FAMS for p in pats_src[f]
               if not any(re.search(p, u or "", re.I) for u in units))

    print("\n" + "-" * 78)
    print("RE-DERIVED, by a second implementation")
    print("-" * 78)
    derived = {"n_steps": len(units), "reasoning_bearing": bearing,
               "family_reach": reach, "triple_co_occurrence": co,
               "min_enclosing_window": d, "dead_patterns": dead}
    for k, v in derived.items():
        print(f"  {k:<24} {v}")

    # ── compare against the committed artifacts ─────────────────────────────
    RES = BACKEND / "eval" / "results" / "mythos5"
    orig = json.loads((RES / "component_reach.json").read_text(encoding="utf-8"))
    sweep = json.loads(
        (RES / "temporal_window_sweep.json").read_text(encoding="utf-8"))

    checks = [
        ("n_steps", derived["n_steps"], orig["n_steps"]),
        ("reasoning_bearing", derived["reasoning_bearing"],
         orig["n_steps_with_thought"]),
        ("recognition", reach["recognition"], orig["family_reach"]["recognition"]),
        ("norm", reach["norm"], orig["family_reach"]["norm"]),
        ("discount", reach["discount"], orig["family_reach"]["discount"]),
        ("triple co-occurrence", co, len(orig["conjunctions"]["all_three"])),
        ("min enclosing window", d, sweep["min_enclosing_window_steps"]),
    ]
    print("\n" + "-" * 78)
    print("AGREEMENT WITH THE ORIGINAL IMPLEMENTATION")
    print("-" * 78)
    bad = 0
    for name, mine, theirs in checks:
        ok = mine == theirs
        bad += not ok
        print(f"  {'ok ' if ok else 'MISMATCH'}  {name:<24} "
              f"re-derived {mine}   committed {theirs}")

    print("\n" + "=" * 78)
    if bad == 0:
        print("Two independent implementations agree on every headline number.")
        print("This rules out single-implementation artifacts, which is the")
        print("class of error that produced two withdrawn claims in this work.")
        print("It is NOT independent replication and must never be described")
        print("as such: the same author wrote both implementations.")
    else:
        print(f"{bad} MISMATCH(ES). The disagreement is the result. Do not")
        print("publish the affected numbers until it is resolved.")
    print("=" * 78)

    # ── replication kit manifest ────────────────────────────────────────────
    kit = {}
    for p in sorted((BACKEND / "eval" / "temporal_locality").glob("*.py")):
        kit[f"script/{p.name}"] = sha256(p)
    for p in sorted((BACKEND / "eval" / "results" / "temporal_locality")
                    .glob("*.json")):
        kit[f"result/{p.name}"] = sha256(p)
    for p in sorted(RES.glob("*.json")):
        kit[f"result/mythos5/{p.name}"] = sha256(p)
    kit["input/rationalization.py"] = sha256(mod)
    kit["input/transcript.jsonl"] = sha256(a.jsonl)
    kit["vocabulary_digest"] = digest_of(pats_src)

    print(f"\nREPLICATION KIT MANIFEST: {len(kit)} entries hashed.")
    print("An external party can verify they hold what we ran before running")
    print("it. The transcript itself is NOT redistributed here: it is the")
    print("developer's to publish, and the hash lets a holder confirm identity.")

    doc = {"_what_this_is": "Implementation-independent re-derivation plus a "
                            "hash manifest for external replication.",
           "_this_is_not_independent_replication": True,
           "_why": "The same author wrote both implementations. Agreement "
                   "rules out single-implementation artifacts and nothing more.",
           "frozen_module_sha256": sha256(mod),
           "vocabulary_digest": digest_of(pats_src),
           "patterns_per_family": {f: len(pats_src[f]) for f in FAMS},
           "rederived": derived,
           "agreement": [{"name": n, "rederived": m, "committed": t,
                          "match": m == t} for n, m, t in checks],
           "mismatches": bad,
           "kit_manifest": kit}
    if a.out:
        a.out.parent.mkdir(parents=True, exist_ok=True)
        a.out.write_text(json.dumps(doc, indent=1), encoding="utf-8")
        print(f"\nwrote {a.out}")
    return 0 if bad == 0 else 1


if __name__ == "__main__":
    raise SystemExit(main())
