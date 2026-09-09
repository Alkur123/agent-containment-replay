# AI Incident Response Sprint (Apart Research / CeSIA, Sept 2026)

This folder documents the analysis behind a submission to the AI Incident Response
Sprint, Track 1 (Containment). It tags the 16-step `eval_containment_2026_07.json`
fixture in this repo against Hugging Face's own published kill-chain phase taxonomy
(recon, rce, dropper, exfil, c2, evasion, k8s, supply-chain, tailscale) and reports
where two independent controls would have ended the session, then ablates both of
them (disable each in turn, and disable both at once) to check that the redundancy
claim holds up as a real ablation, not just a lucky ordering.

## What is and is not reproducible from this repo alone

`hf_phase_matrix.py` is the exact script that produced `hf_phase_matrix.json` and
`hf_phase_matrix_gapcheck.json`. It is included for transparency and audit, not as a
one-command reproduction. It imports `engine.ring12.policy`, `engine.ring12.drift`,
and `engine.ring12.verifier`, none of which are part of this repository's MIT release.
This repo, by design, ships only the rationalization (G5) detector and `trajectory.py`
(see `harness/score.py` and `detector/`), not the full governance architecture. The
two rules that fire in this analysis (`secret_exfil_flow` and `capability_laundering`)
live in the modules that are not public here.

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
  project's cost figure already uses: of 86 benign episodes (18 making
  AWS/cloud-CLI-shaped calls), turning `credential_endpoint` on adds zero new
  kills. Reported as a first data point, not full validation: at n=86 zero
  observed, the honest upper bound is about 3.5% by the rule of three, and none
  of the 18 cloud-CLI-shaped steps surface a literal metadata-endpoint string
  the way a cloud SDK's own internal fetch would if modeled as its own action.
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
