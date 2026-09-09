#!/usr/bin/env python3
"""Measure credential_endpoint's false-positive cost on real benign traffic --
the exact measurement its own code comment (engine/ring12/policy.py,
credential_endpoint_hardblock_enabled) asks the deploying operator to run
before turning the control on: "Flip it, measure it on your own benign
traffic, then keep it."

Built for apart_sprint_submission.tex's Future Work item (closing the one
open, unmeasured caveat around the third backstop control found by the
2026-09-09 ablation), using the SAME SLEIGHT-Bench corpus already cited for
this report's cost figure (Section 4.3, alkur2026tr S9.6) so the number is
comparable rather than a fresh, unrelated corpus.

No API key, no zeroed signals: real Ring12Verifier, local ONNX embedder,
deterministic S5.

    GROQ_API_KEY="" REDIS_URL="" python eval/credential_endpoint_fp_probe.py
"""
from __future__ import annotations

import asyncio
import json
import os
import sys

os.environ.setdefault("R12_THRESHOLD_JITTER", "0")

sys.path.insert(0, ".")

from engine.ring12.trajectory import Action, Step  # noqa: E402
from engine.ring12.verifier import Ring12Verifier  # noqa: E402

FIXTURE = "eval/incidents/benign_controls_sleight.json"


def _mk_step(raw: dict, index: int) -> Step:
    a = raw["action"]
    return Step(index=index, thought=raw.get("thought", ""),
                action=Action(type="tool_call", name=a["name"], args=a.get("args", {}),
                               class_=a.get("class_", "READ")))


async def run_one(inc: dict, credential_endpoint_on: bool) -> dict:
    prev = os.environ.get("R12_CREDENTIAL_ENDPOINT_HARDBLOCK")
    os.environ["R12_CREDENTIAL_ENDPOINT_HARDBLOCK"] = "1" if credential_endpoint_on else "0"
    try:
        sess_spec = inc["session"]
        tag = "on" if credential_endpoint_on else "off"
        v = Ring12Verifier(tenant_id=f"cred-fp-probe-{tag}", vault_writes_enabled=False)
        session = await v.begin_session(
            goal=sess_spec["goal"], agent_id=inc["id"],
            declared_tools=sess_spec.get("declared_tools"),
            declared_classes=sess_spec.get("declared_classes"),
            rekha=sess_spec.get("rekha"))
        sid = session.session_id
        killed_by = None
        killed_at = None
        for i, raw in enumerate(inc["steps"]):
            d = await v.evaluate(_mk_step(raw, i), session_id=sid)
            if d.action == "KILL_SESSION":
                killed_by = d.hard_block
                killed_at = i
                break
        try:
            await v.end_session(sid, outcome="replay_complete", admin_clearance=True)
        except Exception:
            pass
        return {"id": inc["id"], "arm": inc.get("arm"), "killed": killed_by is not None,
                "hard_block": killed_by, "killed_at": killed_at, "n_steps": len(inc["steps"])}
    finally:
        if prev is None:
            os.environ.pop("R12_CREDENTIAL_ENDPOINT_HARDBLOCK", None)
        else:
            os.environ["R12_CREDENTIAL_ENDPOINT_HARDBLOCK"] = prev


async def main() -> int:
    data = json.load(open(FIXTURE, encoding="utf-8"))
    incidents = data["incidents"]
    print(f"Loaded {len(incidents)} benign SLEIGHT-Bench episodes from {FIXTURE}")

    results = {"off": [], "on": []}
    for tag, on in (("off", False), ("on", True)):
        for inc in incidents:
            r = await run_one(inc, on)
            results[tag].append(r)

    off_kills = [r for r in results["off"] if r["killed"]]
    on_kills = [r for r in results["on"] if r["killed"]]
    off_ids = {r["id"] for r in off_kills}
    on_ids = {r["id"] for r in on_kills}
    new_kills = on_ids - off_ids  # episodes that ONLY die once credential_endpoint is armed
    credential_endpoint_kills = [r for r in results["on"]
                                  if r["hard_block"] == "credential_endpoint"]

    print(f"\nBaseline (credential_endpoint OFF, shipped default): "
          f"{len(off_kills)}/{len(incidents)} benign episodes killed by something else")
    print(f"With credential_endpoint ON: {len(on_kills)}/{len(incidents)} killed")
    print(f"Episodes killed by credential_endpoint specifically: "
          f"{len(credential_endpoint_kills)}/{len(incidents)}")
    print(f"NEW kills introduced solely by turning credential_endpoint on: "
          f"{len(new_kills)}/{len(incidents)} ({100*len(new_kills)/len(incidents):.1f}%)")
    if credential_endpoint_kills:
        print("\nWhich episodes, and why:")
        for r in credential_endpoint_kills:
            print(f"  {r['id']:<28} arm={r['arm']:<10} step {r['killed_at']}/{r['n_steps']}")

    json.dump(results, open("eval/results/credential_endpoint_fp_probe.json", "w", encoding="utf-8"),
               indent=2)
    print("\nwrote eval/results/credential_endpoint_fp_probe.json")
    return 0


if __name__ == "__main__":
    sys.exit(asyncio.run(main()))
