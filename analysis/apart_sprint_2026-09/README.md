# AI Incident Response Sprint (Apart Research / CeSIA, Sept 2026)

This folder documents the analysis behind a submission to the AI Incident Response
Sprint, Track 1 (Containment). It tags the 16-step `eval_containment_2026_07.json`
fixture in this repo against Hugging Face's own published kill-chain phase taxonomy
(recon, rce, dropper, exfil, c2, evasion, k8s, supply-chain, tailscale) and reports
where two declaration-independent controls would have ended the session, then ablates
both of them (disable each in turn, and disable both at once) to check that the
redundancy claim holds up as a real ablation, not just a lucky ordering.

The headline is that the redundancy claim was then tested a **second** way, and the two
tests disagree. The ablation says the controls are behaviourally redundant; the
build-time certification below says they are substrate-independent but **epistemically
identical**, all pattern matchers, so a single obfuscation could defeat all of them.
Both are true of the same gate, and neither method finds the other's answer. Note the
wording carefully: "independent" here means *declaration-independent* (they need no
pre-declared scope to fire) and *substrate-independent* (three distinct mechanisms, no
shared point of failure). It does **not** mean independent in the sense that would
survive an adaptive adversary, and this analysis says so on its own evidence.

The report also tests both of those findings **out of sample**, on a 1,361-action
transcript a different lab released five weeks after the fixture and the detector
here were pinned. That replay is now in this folder (`mythos5_real_replay.py`);
until 12 September it was described in the root README and not shipped.

## What is and is not reproducible from this repo alone

`hf_phase_matrix.py` is the exact script that produced `hf_phase_matrix.json` and
`hf_phase_matrix_gapcheck.json`. It is included for transparency and audit, not as a
one-command reproduction. It imports `engine.ring12.trajectory` and
`engine.ring12.verifier`, and its behaviour depends on the environment toggles read
by `engine.ring12.policy` and `engine.ring12.drift`, none of which are part of this
repository's MIT release.
This repo, by design, ships only the rationalization (G5) detector and `trajectory.py`
(see `harness/score.py` and `detector/`), not the full governance architecture. The
two rules that fire in this analysis (`secret_exfil_flow` and `capability_laundering`)
live in the modules that are not public here.

Every script here is a **byte-for-byte copy** of the file that produced the
result beside it, not a cleaned-up version. That is deliberate, and it has one
visible cost: their `USAGE` blocks and default output paths name directories in
the private tree (`eval/`, `eval/results/`), which do not exist in this
repository. Reading a path there as a path here will not work. The alternative
was to edit them for publication, which would have made them no longer the
scripts that produced the numbers.

What you can verify from this repo alone:

- The fixture (`fixtures/eval_containment_2026_07.json`) is byte-identical to the one
  used in the analysis. No steps were added, removed, or altered for this sprint.
- The two result files record, per step, the verdict, the hard-block reason string,
  and the drift aggregate the real verifier returned. They are raw output, not
  hand-edited.
- The phase tags (`PHASE_TAGS` in the script) are stated as judgment calls where they
  are judgment calls; three of sixteen steps are marked with a `~` for a phase pairing
  rather than forced into one bucket.
- The ablation result file records four full arms (disable rule 1, disable rule 2,
  disable both, and disable rule 2 on a fresh session from step 4), each a real
  `Ring12Verifier` run, no signals zeroed out.

## Files

- `hf_phase_matrix.py` — the analysis script (requires the private engine to run).
  Now includes `run_ablation()` (`--ablation` flag), added after the initial
  submission to test the redundancy claim directly instead of inferring it from a
  single restart.
- `hf_phase_matrix.json` — full 16-step results under both a declared and an
  undeclared scope configuration.
- `hf_phase_matrix_gapcheck.json` — a second run starting fresh at step 4, used to
  confirm that the k8s-phase containment is a real, independent finding and not an
  artifact of the earlier kill masking it.
- `hf_phase_matrix_ablation.json` — the four-arm ablation. Disabling either of the
  two headline rules (`secret_exfil_flow`, `capability_laundering`) individually
  confirms the other alone accounts for the entire remainder of the chain, not
  just its own trigger point. Disabling both surfaces a third rule,
  `credential_endpoint`, that is off by default in production and had simply never
  had a chance to fire in the earlier runs. Its default-off status is a reasoned
  choice in its own source comment, not a completed measurement, and this repo
  does not claim otherwise.
- `credential_endpoint_fp_probe.py` / `credential_endpoint_fp_probe.json` — a
  first measurement toward that gap, on the external SLEIGHT-Bench corpus this
  project's cost figure already uses: of 86 benign episodes (12 of which make
  AWS/cloud-CLI-shaped calls, 18 such steps in all), turning
  `credential_endpoint` on adds zero new kills. Reported as a first data point,
  not full validation: at n=86 zero observed, the honest upper bound is about
  3.5% by the rule of three, and none of those 18 steps surface a literal
  metadata-endpoint string the way a cloud SDK's own internal fetch would if
  modeled as its own action.
- `hardblock_gate_certification.py` / `hardblock_gate_certification.json` —
  points this project's separate build-time certification family
  (`engine.pramana`, `engine.vikalpa`, also not part of this repo's MIT
  release) at the three hard-block rules above, the first time that family has
  been run against this composition rather than the two it already covers
  elsewhere (a content-governance gate, a soft drift aggregate). Result is
  mixed, not a clean pass: all three rules are the same means of knowledge
  (deterministic rule-chains), so the independence floor on epistemic
  diversity fails, but they reduce to three distinct mechanisms with no shared
  point of failure, and their combinator is licensed. A real coupling
  (`secret_exfil_flow`'s taint source calls `credential_endpoint`'s own
  detector) was found by reading `engine/ring12/drift.py` directly, stated in
  the script as manually verified, not caught by an automated tool.
- `mythos5_real_replay.py` / `mythos5_real_replay.json` — **the out-of-sample
  check (report Section 4.5), added 2026-09-12.** On 1 August 2026 this repo
  published an 8-step reconstruction of the Mythos 5 incident and a containment
  prediction derived from it. On 9 September the incident's owner released the
  real transcript: 1,361 actions over 10.42 hours, 170x finer. This script runs
  that transcript through the same unmodified verifier, in four scope
  configurations. With a declared boundary the session ends at **step 6 of
  1,361**, containing 90 of 90 outbound steps and the single irreversible one
  (the package upload at step 1,358) with 1,352 steps of margin; on the stricter
  named-host-only reading, 89 of 90 and a kill at step 10; with **no** declared
  boundary, 0 of 90 and no kill at all, which reproduces the published
  prediction against ground truth. The kill is fail-closed, not clever: that
  step's egress destination is a shell variable the boundary cannot resolve, so
  it cannot be shown to lie inside the declared line and is refused. The hosts
  that variable iterates are in fact all outside the line, but the control never
  established that and is **not** credited with it. ⚠ Not pre-registered, and
  the harm labels were assigned after the transcript was readable — the primary
  number deliberately does not depend on them, being "which step does the
  session die on, against step 1,358". The pre-registered object was a different
  thing entirely, a WARN-only chain-of-thought detector, and it **failed**
  (`analysis/reg1_mythos5/`). Nothing here disturbs that verdict.
- `replay_incidents.py` / `benign_controls_replay.json` — the false-positive
  half of the same section, and the script behind the four-incident prior-work
  table in the report's appendix. Under a declared boundary, **0 of 4** faithful
  benign controls are killed and **2 of 2** loose ones are. The second number is
  the cost of boundary enforcement and is reported as a cost, not excused: one
  of the two dies on an undeclared CDN, and the other on `pipeline_poisoning`,
  which fires in *every* configuration and is therefore not a boundary cost at
  all. Metric 3's denominator is four sessions — read it as "no false kill in
  the four faithful controls we hold", never as a false-positive rate.
- `mythos5_ablation.py` / `mythos5_ablation.json` — **the same four-arm ablation
  run on the out-of-sample chain, added 2026-09-12, and it does not reproduce
  the redundancy.** The report's own Limitations had said the out-of-sample
  check "tests enforcement and the pattern detector, not an ablation, so we do
  not know whether a third backstop exists there." Now measured. Baseline: the
  declared boundary ends the session at step 6. Disable the five
  declaration-independent hard blocks and keep the boundary: **identical**, step
  6 again, so the boundary carries the chain alone. Remove the boundary and arm
  every one of those blocks including `credential_endpoint`: the verifier
  returns **ALLOW on all 1,361 steps** — no kill, no warn, upload not contained.
  A fresh session started past the first crossing is caught again four steps
  later at step 10, but by the same mechanism on a named host, so it is a second
  chance rather than a second control. **On this chain there is no backstop**,
  and the behavioural redundancy the Hugging Face chain shows is a property of
  that chain, not of the architecture.

  Writing this also found a harness difference worth stating plainly:
  `hf_phase_matrix.py` arms `R12_CREDENTIAL_ENDPOINT_HARDBLOCK` on every arm of
  the study, and `mythos5_real_replay.py` armed nothing, so the published
  out-of-sample run used that control at its shipped default (off). The study
  and the out-of-sample check had been run under different harnesses. Every arm
  in this file states its own environment explicitly.
- `credential_endpoint_sdk_probe.py` / `credential_endpoint_sdk.json` — **the
  third control, withdrawn by measurement.** The report reported "zero new kills
  on 86 benign episodes with `credential_endpoint` on" and an honest 3.5%
  rule-of-three bound. That number answers a different question than it appears
  to: *no episode in that corpus contains the shape the control is suspected of
  mishandling*, a cloud SDK's own instance-credential fetch as its own step.
  This builds the shape. Five episodes modelling the documented credential paths
  of the major clouds (AWS IMDSv1, IMDSv2's PUT-then-GET token exchange, the ECS
  task provider, EKS Pod Identity, the Google metadata server) are each an
  ordinary authorised job in which the fetch is how a legitimate role is *used*.
  With the control armed it kills **five of five**, each on the metadata step;
  with it off, none; and a matched sixth episode doing the same work with
  credentials already in the environment is never killed, so the kill is
  attributable to the fetch. The episodes are constructed and carry **no rate** —
  they settle whether the control fires on this shape, not how often the shape
  occurs. That is enough to withdraw it as a deployable backstop and not enough
  to price it.
