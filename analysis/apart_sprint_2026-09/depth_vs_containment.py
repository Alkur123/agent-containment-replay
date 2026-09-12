"""Depth and containment are different axes. Put them side by side.

WHY THIS EXISTS
---------------
`redundancy_depth.py` measures how many mechanisms EACH ALONE account for a
chain, in the declaration-independent setting. It found depth ranging 0 to 4 and
that was reported as the redundancy claim failing to transfer.

Read alone, that is misleading, and this file exists because the omission was
pointed out. Depth 0 does not mean the chain runs to completion. It means no
DECLARATION-INDEPENDENT rule fires, and on those chains a declared scope
boundary is what stops it -- often earlier than any rule does. Reporting the
count without the outcome invites the reading that the architecture failed on
three of five chains, which is not what happened.

This joins the two: per chain, the depth, and what the shipped configuration
actually contained. The question a containment standard has to answer is not
"how many rules fired" but "was the irreversible act stopped", and those two
come apart here.

USAGE
    cd backend
    REDIS_URL="" OPENAI_API_KEY="" R12_THRESHOLD_JITTER=0 \
      python eval/depth_vs_containment.py \
             --out eval/results/mythos5/depth_vs_containment.json
"""

from __future__ import annotations

import argparse
import json
import pathlib
import sys

HERE = pathlib.Path(__file__).resolve().parent
RESULTS = HERE / "results"

# The real 1,361-action trace is replayed by mythos5_real_replay.py, not by the
# fixture replay, so its row is read from that result file.
REAL_TRACE = RESULTS / "mythos5" / "real_replay.json"
FIXTURE_REPLAY = RESULTS / "incident_replay_2026-08-01.json"
DEPTH = RESULTS / "mythos5" / "redundancy_depth.json"

LABELS = {
    "openai-hf-2026-07": "OpenAI to Hugging Face",
    "anthropic-i1-opus47": "Anthropic i1, named collision",
    "anthropic-i2-mythos5": "Anthropic i2, PyPI (8-step reconstruction)",
    "anthropic-i3-internal": "Anthropic i3, ~9,000-target scan",
}


def main() -> int:
    ap = argparse.ArgumentParser()
    ap.add_argument("--out", type=pathlib.Path)
    a = ap.parse_args()

    depth = json.loads(DEPTH.read_text(encoding="utf-8"))["depth_by_incident"]
    runs = json.loads(FIXTURE_REPLAY.read_text(encoding="utf-8"))["runs"]
    declared = {r["incident"]: r for r in runs if r["config"] == "declared"}
    undeclared = {r["incident"]: r for r in runs if r["config"] == "none"}

    rows = []
    for inc, label in LABELS.items():
        d = declared[inc]
        u = undeclared[inc]
        rows.append({
            "chain": label,
            "incident": inc,
            "depth_declaration_independent": depth[inc],
            "declared_kill_index": d["first_kill_index"],
            "declared_irreversible_contained": d["irreversible_contained"],
            "declared_irreversible_total": d["irreversible_total"],
            "declared_harmful_contained": d["harmful_contained"],
            "declared_harmful_total": d["harmful_total"],
            "undeclared_irreversible_contained": u["irreversible_contained"],
            "undeclared_irreversible_total": u["irreversible_total"],
        })

    real = json.loads(REAL_TRACE.read_text(encoding="utf-8"))["configs"]
    rows.append({
        "chain": "Anthropic i2, real 1,361-action trace",
        "incident": "anthropic-i2-mythos5-real",
        "depth_declaration_independent": 0,
        "declared_kill_index": real["declared"]["first_kill_index"],
        "declared_irreversible_contained": real["declared"]["irreversible_contained"],
        "declared_irreversible_total": real["declared"]["irreversible_total"],
        "declared_harmful_contained": real["declared"]["harmful_contained"],
        "declared_harmful_total": real["declared"]["harmful_total"],
        "undeclared_irreversible_contained": real["none"]["irreversible_contained"],
        "undeclared_irreversible_total": real["none"]["irreversible_total"],
    })

    irr_c = sum(r["declared_irreversible_contained"] for r in rows)
    irr_t = sum(r["declared_irreversible_total"] for r in rows)
    un_c = sum(r["undeclared_irreversible_contained"] for r in rows)
    un_t = sum(r["undeclared_irreversible_total"] for r in rows)
    depths = sorted(r["depth_declaration_independent"] for r in rows)

    print("=" * 96)
    print("DEPTH vs CONTAINMENT -- the two come apart")
    print("=" * 96)
    print(f"{'chain':<44s} {'depth':>5s} {'kill':>5s} {'irrev (declared)':>18s} {'irrev (none)':>14s}")
    for r in rows:
        k = r["declared_kill_index"]
        print(f"{r['chain']:<44s} {r['depth_declaration_independent']:>5d} "
              f"{str(k):>5s} "
              f"{r['declared_irreversible_contained']:>9d}/{r['declared_irreversible_total']:<8d}"
              f"{r['undeclared_irreversible_contained']:>7d}/{r['undeclared_irreversible_total']}")

    verdict = (
        f"Across {len(rows)} chains, declaration-independent depth ranges "
        f"{depths[0]} to {depths[-1]}, while a declared scope boundary contains "
        f"{irr_c} of {irr_t} irreversible actions. Without a declared boundary the same "
        f"chains contain {un_c} of {un_t}. Depth and containment are different axes: the "
        f"count of independently sufficient rules is chain-specific and does not "
        f"generalise, and the declared boundary is what does. A defense-in-depth "
        f"claim that counts rules is measuring the axis that does not carry."
    )
    print("\n" + "-" * 96)
    print(verdict)
    print("-" * 96)

    out = {
        "_what_this_is": (
            "Per chain: declaration-independent depth beside what the shipped declared "
            "configuration actually contained. Written because reporting depth alone "
            "invited the reading that the architecture failed on the depth-0 chains, "
            "which is not what the containment numbers say."
        ),
        "_sources": {
            "depth": "redundancy_depth.json",
            "four reconstructions": "incident_replay_2026-08-01.json (config=declared)",
            "real trace": "mythos5/real_replay.json (config=declared)",
        },
        "declared_irreversible_contained": f"{irr_c}/{irr_t}",
        "undeclared_irreversible_contained": f"{un_c}/{un_t}",
        "depth_range": [depths[0], depths[-1]],
        "verdict": verdict,
        "rows": rows,
    }
    if a.out:
        a.out.parent.mkdir(parents=True, exist_ok=True)
        a.out.write_text(json.dumps(out, indent=1), encoding="utf-8")
        print(f"\nwrote {a.out}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
