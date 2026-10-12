# Registration 1 on the Mythos 5 transcript: per-incident measurements

Statistics only. No transcript text appears in any file here; the transcript
carries a canary and a request not to appear in training corpora, and it is not
redistributed. Fetch it from its developer:

    https://github.com/anthropics/mythos-5-incident-transcript  (commit 62858fc)

## Which file holds what

| result | produced by | reproduces from this repository alone? |
|---|---|---|
| `results/component_reach.json` (per-family reach, co-occurrence) | `scripts/mythos5_component_reach.py` | yes, byte-identical |
| `results/conjunct_timing.json` (68 steps / 0.59 h; 371 / 2.66 h causal) | `scripts/mythos5_conjunct_timing.py` | yes, byte-identical |
| `results/temporal_window_sweep.json` (encloses / benign bound by W) | `scripts/mythos5_temporal_window_sweep.py` | yes, byte-identical |
| `results/action_channel.json` (reasoning vs tool channels) | `scripts/mythos5_action_channel.py` | yes, byte-identical |
| `results/registered_constants.json` (threshold, saturation, multiplier) | `scripts/mythos5_registered_constants.py` | yes, given LF checkouts (see below) |
| `results/step35_counterfactual.json` (0.4900 < 0.55) | `scripts/mythos5_step35_counterfactual.py` | yes, byte-identical |
| `results/b3_length_response.json`, `results/session_feasibility.json` | the registered session-scoped repair | results only: the repair module is not in this repository |
| `results/current_detector.json` | the shipped successor detector | results only: the shipped module is not in this repository |
| `results/real_replay.json` | the full containment runtime | results only: not pre-registered, see the paper |

"Byte-identical" was checked on 2026-10-13 by running each script in a fresh
clone of this repository against the transcript at commit `62858fc` and
comparing with the committed file.

```sh
python analysis/reg1_mythos5/convert_mythos5.py --jsonl transcript.jsonl --out steps.json
python analysis/reg1_mythos5/scripts/mythos5_component_reach.py --steps steps.json --out out.json
python analysis/reg1_mythos5/scripts/mythos5_conjunct_timing.py --jsonl transcript.jsonl --out out.json
```

## Two hashes, and line endings

* `detector/score_transcript.py` refuses to score unless the detector's SHA-256
  is `f988b52a...`, which is the hash over **LF** line endings. Before
  2026-10-13 a fresh clone on Windows with Git's default `core.autocrlf=true`
  received CRLF line endings and the scorer refused to run. `.gitattributes`
  now forces LF checkouts on every platform.
* The replication manifest in `analysis/temporal_locality/tl6_rederive.json`
  pins the transcript at `2c749d03...`, which is its hash with **CRLF** line
  endings. The file as the developer's repository serves it has SHA-256
  `6f2a5a50b53640bd779a198cef8a620f2d6e2bbaaf4a0dea9edac87a69fc3e4b`; the two
  differ only in line endings. The same manifest pins `input/rationalization.py`
  to the shipped detector module, whose three pattern lists are identical
  (compared as parsed syntax trees) to the frozen module in `detector/`.
