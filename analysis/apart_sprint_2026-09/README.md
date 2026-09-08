# AI Incident Response Sprint (Apart Research / CeSIA, Sept 2026)

This folder documents the analysis behind a submission to the AI Incident Response
Sprint, Track 1 (Containment). It tags the 16-step `eval_containment_2026_07.json`
fixture in this repo against Hugging Face's own published kill-chain phase taxonomy
(recon, rce, dropper, exfil, c2, evasion, k8s, supply-chain, tailscale) and reports
where two independent controls would have ended the session.

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

## Files

- `hf_phase_matrix.py` — the analysis script (requires the private engine to run).
- `hf_phase_matrix.json` — full 16-step results under both a declared and an
  undeclared scope configuration.
- `hf_phase_matrix_gapcheck.json` — a second run starting fresh at step 4, used to
  confirm that the k8s-phase containment is a real, independent finding and not an
  artifact of the earlier kill masking it.
