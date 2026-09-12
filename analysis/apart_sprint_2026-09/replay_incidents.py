"""Replay the July 2026 evaluation-containment incidents through R12/R13.

Turns the "would have caught it" column of
`docs/INCIDENT_2026-07_HF_AGENT_INTRUSION_ANALYSIS.md` into measured numbers.

WHAT THIS MEASURES, AND WHAT IT DOES NOT
-----------------------------------------
It measures: given the action sequence a public postmortem reports, at which
step does Ring 12 first fire, and how much of the reported harm falls after
that point. It runs the real, unmodified verifier.

It does NOT measure: whether Chakravyuha would have stopped the real incident.
The fixture is a reconstruction at postmortem granularity (16 steps standing in
for ~6,280 action clusters, in the Hugging Face case), the thoughts are mostly
reconstructed, and neither agent was adversarial to a monitor. Every number
this script prints is a statement about the reconstruction. Report it that way
or not at all.

THE ABLATION IS THE POINT
--------------------------
Each incident runs in three configurations, and the three are chosen so the
table isolates WHICH ring does the work rather than just showing a good number:

  none      — every tool and class the trajectory uses is declared in advance,
              and there is no boundary set. The scope gate therefore cannot
              fire, and ONLY the declaration-independent rings are live
              (privesc, secret-exfil flow, provenance, credential endpoint,
              rationalisation). This is the honest analogue of what both eval
              harnesses had: the agent was free to act, containment was a
              sentence in the prompt. It is also the column that re-tests this
              project's own 2026-06-06 manifest-scope finding — that a faithful
              declaration silences the scope gate and relocates all harm-catch
              onto the flow rings.

  inferred  — no manifest at all, so the verifier falls back to inferring
              expected tools/classes from the goal text. This is R12's default
              path for an un-instrumented agent. It fires early and noisily;
              read its numbers as "a scope gate against a scope nobody
              declared", not as a clean detection result.

  declared  — an explicit tool manifest, explicit action classes, AND a
              Lakshmaṇa-Rekhā boundary set naming the exercise range. This is
              the configuration the analysis argues an eval harness should run.

The `none` -> `declared` gap is the thesis in one table: the failure was not
that the models were insufficiently aligned, it was that the boundary was a
sentence rather than a control.

`--no-g5` re-runs with the rationalisation detector disabled, so its
contribution can be attributed instead of assumed.

USAGE
    cd backend
    GROQ_API_KEY="" REDIS_URL="" python eval/replay_incidents.py
    GROQ_API_KEY="" REDIS_URL="" python eval/replay_incidents.py --json out.json
    GROQ_API_KEY="" REDIS_URL="" python eval/replay_incidents.py --no-g5
    GROQ_API_KEY="" REDIS_URL="" python eval/replay_incidents.py --incident anthropic-i2-mythos5 --verbose
"""

from __future__ import annotations

import argparse
import asyncio
import json
import os
import sys
from dataclasses import dataclass, field, asdict
from pathlib import Path
from typing import Dict, List, Optional

# Deterministic replay. Threshold jitter is unseedable (SystemRandom), so a
# near-boundary step would make the measured catch-index flap between runs.
os.environ.setdefault("R12_THRESHOLD_JITTER", "0")
os.environ.setdefault("R12_ADAPTIVE_DEPTH", "1")
# The gaps this fixture was built to exercise. Both default OFF in production
# for measured reasons (see policy.credential_endpoint_hardblock_enabled); the
# replay arms them explicitly so the table shows what they do, and the summary
# labels the configuration.
os.environ.setdefault("R12_CREDENTIAL_ENDPOINT_HARDBLOCK", "1")
os.environ.setdefault("R12_SHELL_SECRET_HARDBLOCK", "1")

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

from engine.ring12.trajectory import Action, Step          # noqa: E402
from engine.ring12.verifier import Ring12Verifier          # noqa: E402

FIXTURE = Path(__file__).parent / "incidents" / "eval_containment_2026_07.json"
BENIGN  = Path(__file__).parent / "incidents" / "benign_controls_2026_08.json"

# Ordered worst-instrumented to best-instrumented; the table reads as a ladder.
_CONFIGS = ("none", "inferred", "declared")


@dataclass
class StepResult:
    index: int
    note: str
    tool: str
    cls: str
    harmful: bool
    irreversible: bool
    verdict: str
    hard_block: Optional[str]
    reason: str
    aggregate: float
    contained: bool = False       # did a PRIOR step already kill the session?


@dataclass
class RunResult:
    incident: str
    config: str
    steps: List[StepResult] = field(default_factory=list)
    first_fire_index: Optional[int] = None      # first WARN or KILL
    first_kill_index: Optional[int] = None      # first KILL_SESSION
    harmful_total: int = 0
    harmful_before_kill: int = 0
    harmful_contained: int = 0
    irreversible_total: int = 0
    irreversible_contained: int = 0

    @property
    def containment_rate(self) -> float:
        if not self.harmful_total:
            return 0.0
        return self.harmful_contained / self.harmful_total

    @property
    def irreversible_containment_rate(self) -> float:
        if not self.irreversible_total:
            return 0.0
        return self.irreversible_contained / self.irreversible_total


def _mk_step(raw: dict, index: int) -> Step:
    a = raw["action"]
    return Step(
        index=index,
        thought=raw.get("thought", ""),
        action=Action(
            type="tool_call",
            name=a["name"],
            args=a.get("args", {}),
            class_=a.get("class_", "READ"),
        ),
    )


async def _run_one(incident: dict, config: str) -> RunResult:
    """Replay one incident in one configuration against a real verifier."""
    sess_spec = incident["session"]
    res = RunResult(incident=incident["id"], config=config)

    v = Ring12Verifier(tenant_id=f"replay-{config}", vault_writes_enabled=False)

    if config == "declared":
        session = await v.begin_session(
            goal=sess_spec["goal"],
            agent_id=incident["id"],
            declared_tools=sess_spec.get("declared_tools"),
            declared_classes=sess_spec.get("declared_classes"),
            rekha=sess_spec.get("rekha"),
        )
    elif config == "none":
        # Declare EXACTLY what the trajectory uses, and no boundary set. The
        # scope gate is thereby satisfied on every step and cannot fire, which
        # isolates the declaration-independent rings. Not "no config" — a
        # deliberately maximally-permissive one.
        used_tools = sorted({s["action"]["name"] for s in incident["steps"]})
        used_classes = sorted({s["action"].get("class_", "READ")
                               for s in incident["steps"]})
        session = await v.begin_session(
            goal=sess_spec["goal"],
            agent_id=incident["id"],
            declared_tools=used_tools,
            declared_classes=used_classes,
        )
    else:  # "inferred" — no manifest; the verifier infers scope from the goal.
        session = await v.begin_session(
            goal=sess_spec["goal"],
            agent_id=incident["id"],
        )
    sid = session.session_id

    killed_at: Optional[int] = None
    for i, raw in enumerate(incident["steps"]):
        harmful = bool(raw.get("harmful"))
        irreversible = bool(raw.get("irreversible"))
        if harmful:
            res.harmful_total += 1
        if irreversible:
            res.irreversible_total += 1

        already_contained = killed_at is not None
        if already_contained:
            # Session is dead. R13 refuses further egress; we do not re-score.
            sr = StepResult(
                index=i, note=raw.get("note", ""), tool=raw["action"]["name"],
                cls=raw["action"].get("class_", "READ"), harmful=harmful,
                irreversible=irreversible, verdict="CONTAINED",
                hard_block=None, reason=f"session killed at step {killed_at}",
                aggregate=0.0, contained=True,
            )
            res.steps.append(sr)
            if harmful:
                res.harmful_contained += 1
            if irreversible:
                res.irreversible_contained += 1
            continue

        d = await v.evaluate(_mk_step(raw, i), session_id=sid)
        sr = StepResult(
            index=i, note=raw.get("note", ""), tool=raw["action"]["name"],
            cls=raw["action"].get("class_", "READ"), harmful=harmful,
            irreversible=irreversible, verdict=d.action,
            hard_block=d.hard_block, reason=d.reason,
            aggregate=getattr(d.drift, "aggregate", 0.0),
        )
        res.steps.append(sr)

        if harmful:
            res.harmful_before_kill += 1
        if d.action in ("WARN", "KILL_SESSION") and res.first_fire_index is None:
            res.first_fire_index = i
        if d.action == "KILL_SESSION":
            killed_at = i
            if res.first_kill_index is None:
                res.first_kill_index = i

    try:
        await v.end_session(sid, outcome="replay_complete", admin_clearance=True)
    except Exception:
        pass
    return res


# ── Reporting ────────────────────────────────────────────────────────────────

def _fmt_table(runs: List[RunResult]) -> str:
    by_incident: Dict[str, Dict[str, RunResult]] = {}
    for r in runs:
        by_incident.setdefault(r.incident, {})[r.config] = r

    w = 34
    out = []
    out.append("")
    out.append("=" * 96)
    out.append("EVALUATION-CONTAINMENT INCIDENT REPLAY — measured on the reconstruction")
    out.append("=" * 96)
    out.append(f"{'incident':<{w}} {'config':<10} {'1st fire':>9} {'1st kill':>9} "
               f"{'harm contained':>15} {'irrev contained':>16}")
    out.append("-" * 96)
    for inc, cfgs in by_incident.items():
        for cfg in _CONFIGS:
            r = cfgs.get(cfg)
            if r is None:
                continue
            fire = "-" if r.first_fire_index is None else f"#{r.first_fire_index}"
            kill = "-" if r.first_kill_index is None else f"#{r.first_kill_index}"
            out.append(
                f"{inc:<{w}} {cfg:<10} {fire:>9} {kill:>9} "
                f"{r.harmful_contained:>3}/{r.harmful_total:<3} "
                f"({r.containment_rate:>5.1%}) "
                f"{r.irreversible_contained:>3}/{r.irreversible_total:<3} "
                f"({r.irreversible_containment_rate:>5.1%})"
            )
        out.append("-" * 96)
    return "\n".join(out)


def _fmt_benign(runs: List[RunResult], incidents: list) -> str:
    """Precision view. Any KILL on benign traffic is a false positive; the two
    arms differ only in whether the FP has a defence."""
    arm_of = {i["id"]: i.get("arm", "faithful") for i in incidents}
    out = ["", "=" * 96,
           "BENIGN CONTROL SET — precision, not catch",
           "=" * 96,
           f"{'session':<32} {'arm':<10} {'config':<10} {'verdict':<12} "
           f"{'FP step':>8}  what fired"]
    out.append("-" * 96)
    tally = {}
    for r in runs:
        arm = arm_of.get(r.incident, "faithful")
        killed = [s for s in r.steps if s.verdict == "KILL_SESSION"]
        warned = [s for s in r.steps if s.verdict == "WARN"]
        if killed:
            verdict, idx = "FALSE KILL", f"#{killed[0].index}"
            what = killed[0].hard_block or killed[0].reason[:44]
        elif warned:
            verdict, idx = "warn only", f"#{warned[0].index}"
            what = (warned[0].hard_block or warned[0].reason[:44])
        else:
            verdict, idx, what = "clean", "-", ""
        key = (arm, r.config)
        t = tally.setdefault(key, {"n": 0, "kill": 0, "warn": 0})
        t["n"] += 1
        t["kill"] += 1 if killed else 0
        t["warn"] += 1 if (warned and not killed) else 0
        out.append(f"{r.incident:<32} {arm:<10} {r.config:<10} {verdict:<12} "
                   f"{idx:>8}  {what}")
    out.append("-" * 96)
    out.append("")
    out.append("SUMMARY (a kill on benign traffic is a false positive in BOTH arms;")
    out.append("         the arms differ only in whether the FP has a defence)")
    for (arm, cfg), t in sorted(tally.items()):
        rate = t["kill"] / t["n"] if t["n"] else 0.0
        out.append(f"  arm={arm:<10} config={cfg:<10} "
                   f"false kills {t['kill']}/{t['n']} ({rate:>5.1%})   "
                   f"warn-only {t['warn']}/{t['n']}")
    return chr(10).join(out)


def _fmt_detail(r: RunResult) -> str:
    out = [f"\n### {r.incident}  [{r.config}]"]
    for s in r.steps:
        mark = "!" if s.harmful else " "
        irr = "*" if s.irreversible else " "
        out.append(f"  {mark}{irr} #{s.index:<2} {s.verdict:<13} "
                   f"{s.tool:<14} agg={s.aggregate:.3f}  {s.note[:52]}")
        if s.hard_block:
            out.append(f"        -> hard_block={s.hard_block}: {s.reason[:110]}")
        elif s.verdict == "WARN":
            out.append(f"        -> {s.reason[:110]}")
    return "\n".join(out)


async def main_async(args) -> int:
    if args.benign_file:
        src, args.benign = args.benign_file, True
    else:
        src = BENIGN if args.benign else FIXTURE
    data = json.loads(src.read_text(encoding="utf-8"))
    incidents = data["incidents"]
    if args.incident:
        incidents = [i for i in incidents if i["id"] == args.incident]
        if not incidents:
            print(f"no such incident: {args.incident}", file=sys.stderr)
            return 2

    runs: List[RunResult] = []
    for inc in incidents:
        for cfg in _CONFIGS:
            runs.append(await _run_one(inc, cfg))

    if args.benign:
        print(_fmt_benign(runs, incidents))
    else:
        print(_fmt_table(runs))
    if args.verbose:
        for r in runs:
            print(_fmt_detail(r))

    if "provenance" not in data:
        print("")
        print("DESIGN: " + str(data.get("design_note",""))[:280])
    else:
        print("")
        print("PROVENANCE: " + data["provenance"]["statement"][:200])
        print("LIMITS:     " + str(data["provenance"].get("limits") or data["provenance"].get("statement",""))[:200])
    print(f"\nconfig: R12_CREDENTIAL_ENDPOINT_HARDBLOCK="
          f"{os.environ.get('R12_CREDENTIAL_ENDPOINT_HARDBLOCK')} "
          f"R12_SHELL_SECRET_HARDBLOCK={os.environ.get('R12_SHELL_SECRET_HARDBLOCK')} "
          f"R12_ADAPTIVE_DEPTH={os.environ.get('R12_ADAPTIVE_DEPTH')} "
          f"jitter={os.environ.get('R12_THRESHOLD_JITTER')}")

    if args.json:
        payload = {
            "dataset": data.get("dataset", "unknown"),
            "version": data.get("version", "generated"),
            "provenance": data.get("provenance", {"design_note": data.get("design_note")}),
            "config": {
                k: os.environ.get(k) for k in (
                    "R12_CREDENTIAL_ENDPOINT_HARDBLOCK", "R12_SHELL_SECRET_HARDBLOCK",
                    "R12_ADAPTIVE_DEPTH", "R12_THRESHOLD_JITTER",
                    "R12_RATIONALIZATION_ENABLED")
            },
            "runs": [
                {**{k: v for k, v in asdict(r).items() if k != "steps"},
                 "containment_rate": r.containment_rate,
                 "irreversible_containment_rate": r.irreversible_containment_rate,
                 "steps": [asdict(s) for s in r.steps]}
                for r in runs
            ],
        }
        Path(args.json).write_text(json.dumps(payload, indent=2), encoding="utf-8")
        print(f"\nwrote {args.json}")
    return 0


def main() -> int:
    p = argparse.ArgumentParser(description=__doc__,
                                formatter_class=argparse.RawDescriptionHelpFormatter)
    p.add_argument("--incident", help="replay only this incident id")
    p.add_argument("--benign-file", type=Path,
                   help="score an alternative benign control set (e.g. one "
                        "generated with independent provenance)")
    p.add_argument("--benign", action="store_true",
                   help="run the BENIGN CONTROL set instead: measures precision, "
                        "not catch. A kill in the `faithful` arm is an "
                        "unambiguous false positive.")
    p.add_argument("--verbose", action="store_true", help="per-step detail")
    p.add_argument("--no-g5", action="store_true",
                   help="disable the rationalisation detector (attribution ablation)")
    p.add_argument("--json", help="write the full result to this path")
    args = p.parse_args()
    if args.no_g5:
        os.environ["R12_RATIONALIZATION_ENABLED"] = "0"
    return asyncio.run(main_async(args))


if __name__ == "__main__":
    raise SystemExit(main())
