#!/usr/bin/env python3
"""Point the pramana/vikalpa build-time certification family at the three
hard-block rules this project's Apart-sprint containment report is actually
about, for the first time.

Every prior use of this certification family targets one of two OTHER
compositions already shipped in engine/vikalpa.py: Ring 8's content-governance
gate (policy + paraphrase-stability + post-gen reclassify) and Ring 12's soft
DRIFT AGGREGATE (the weighted sum of s1..s5 signals). Neither of those is the
composition that actually fired in the Hugging Face replay: the three
HARD-BLOCK rules (secret_exfil_flow, capability_laundering,
credential_endpoint) that live in engine/ring12/policy.py's decide() and run
BEFORE the aggregate, bypassing it entirely. This script builds that
composition and certifies it for real -- R1/R2 (pramana.py) and R5-a/e/d/b/c
plus R6 (vikalpa.py) -- rather than asserting what the result would be.

Substrate/pramana labels below were assigned by reading engine/ring12/drift.py
directly (line numbers cited in comments), not by an automated tool:
pramana_substrate.py's existing import-graph walker operates at file
granularity, and all three detector functions live in the SAME file
(drift.py), so it cannot distinguish them here -- a real, stated limitation
of applying the existing tool unmodified to this composition, not a defect
papered over. A genuine coupling was found by reading the code: drift.py:568
(is_secret_access, the taint source secret_exfil_flow reads) calls
detect_credential_endpoint_access directly as one of its three OR'd taint
conditions. Two readings are run, exactly as engine/vikalpa.py's own
certify_chakravyuha_gate_r5(transitive_class=...) runs two readings of Ring
8's dependence partition: NAIVE (three declared substrates, the coupling not
declared) and COUPLING-AWARE (secret_exfil_flow and credential_endpoint
placed in one substrate_class, reflecting the drift.py:568 call).

    GROQ_API_KEY="" REDIS_URL="" python eval/hardblock_gate_certification.py
"""
from __future__ import annotations

import json
import sys

sys.path.insert(0, ".")

from engine.pramana import (  # noqa: E402
    EnactmentRole, EvidenceSource, GateComposition, OnUnavailable, Pramana, certify,
)
from engine.vikalpa import AggregationKind, Combinator, certify_r5  # noqa: E402

GATE_NAME = "r12_hardblock_chain_openai_hf_2026_07"

# All three are deterministic rule-chains over parsed action structure -- none
# is a classifier/embedder score (PRATYAKSA), a comparison against the
# session's own declared plan (SABDA), or analogical retrieval (UPAMANA).
# Declaring any of them otherwise would overstate what they are; see
# pramana.py's own YUKTI note on the same discipline.
_PRAMANA = Pramana.ANUMANA


def _naive_sources() -> tuple[EvidenceSource, ...]:
    """Reading 1: each rule's own primary mechanism, undeclared coupling."""
    return (
        EvidenceSource(
            name="secret_exfil_flow", pramana=_PRAMANA,
            substrate="secret_taint_and_egress_flow",
            description="drift.py:786 detect_secret_exfil_flow -- taint "
                        "(drift.py:550 is_secret_access) + external-egress "
                        "destination check (drift.py:591 _EGRESS_CLASSES).",
        ),
        EvidenceSource(
            name="capability_laundering", pramana=_PRAMANA,
            substrate="sensitive_path_and_pattern_list",
            description="drift.py:303 detect_capability_laundering -- "
                        "drift.py:239 _LAUNDERING_PATHS / :246 "
                        "_LAUNDERING_PATTERNS, plus a workspace-escape check.",
        ),
        EvidenceSource(
            name="credential_endpoint", pramana=_PRAMANA,
            substrate="credential_endpoint_literals",
            description="drift.py:724 detect_credential_endpoint_access -- "
                        "drift.py:666 _CREDENTIAL_ENDPOINT_LITERALS, a fixed "
                        "set of cloud metadata addresses/paths.",
        ),
    )


def _coupling_aware_sources() -> tuple[EvidenceSource, ...]:
    """Reading 2: secret_exfil_flow and credential_endpoint share a class,
    reflecting the measured drift.py:568 call (is_secret_access ->
    detect_credential_endpoint_access, one of three OR'd taint conditions)."""
    naive = _naive_sources()
    out = []
    for s in naive:
        cls = "egress_flow_or_credential_endpoint" if s.name in (
            "secret_exfil_flow", "credential_endpoint") else None
        out.append(EvidenceSource(
            name=s.name, pramana=s.pramana, substrate=s.substrate,
            substrate_class=cls, description=s.description,
        ))
    return tuple(out)


# policy.py's decide(): each hard block is checked in sequence and the first
# hit returns immediately (KILL). Equivalently: ALLOW iff every rule reports
# no-hit -- a logical AND over "rule says no-hit", structurally identical to
# Ring 8's `all_pass = len(failures) == 0` (see engine/vikalpa.py
# RING8_COMBINATOR / certify_chakravyuha_gate_r5's own docstring).
COMBINATOR = Combinator(kind=AggregationKind.AND)


def _run(label: str, sources: tuple[EvidenceSource, ...]) -> dict:
    composition = GateComposition(gate_name=f"{GATE_NAME}_{label}", sources=sources)
    r1r2 = certify(composition)
    r5 = certify_r5(composition, combinator=COMBINATOR)
    return {
        "label": label,
        "r1_r2": r1r2.as_dict(),
        "r5": {
            "gate": r5.gate_name,
            "passed": r5.passed,
            "findings": [f.as_dict() for f in r5.findings],
        },
    }


def main() -> int:
    results = {
        "naive": _run("naive", _naive_sources()),
        "coupling_aware": _run("coupling_aware", _coupling_aware_sources()),
    }
    for label, r in results.items():
        print(f"\n{'='*90}\n{label.upper()}\n{'='*90}")
        print("R1/R2 (pramana.certify):")
        print(f"  passed: {r['r1_r2']['passed']}")
        print(f"  distinct_pramana: {r['r1_r2']['distinct_pramana']}")
        print(f"  substrates: {r['r1_r2']['substrates']}")
        print(f"  failures: {r['r1_r2']['failures']}")
        print(f"  advisories: {r['r1_r2']['advisories']}")
        print("R5/R6 (vikalpa.certify_r5):")
        print(f"  passed: {r['r5']['passed']}")
        for f in r["r5"]["findings"]:
            print(f"  [{f['severity']:<10}] {f['rule']}: {f['reason'][:200]}")

    json.dump(results, open("eval/results/hardblock_gate_certification.json", "w",
                              encoding="utf-8"), indent=2)
    print("\nwrote eval/results/hardblock_gate_certification.json")
    return 0


if __name__ == "__main__":
    sys.exit(main())
