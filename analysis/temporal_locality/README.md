# Temporal locality: the follow-up programme

The pre-registered detector failed on the released transcript (0 fires in 1,361
steps), and the reason was not the vocabulary. These scripts test whether that
finding survives contact with things other than the incident it came from.

**Everything here emits statistics only.** No transcript text, no corpus text.
The released transcript is not redistributed: it is the developer's to publish.

## What each script does

| script | question | headline |
|---|---|---|
| `tl1_shuffle.py` | is the separation ours, or the trajectory's? | Content fixed, arrangement permuted: detection moves from W=5 (d=2) to W=100 (d=68) to W=500 (d=431). Against 10,000 random rearrangements the observed 68 sits at the **60th percentile** — the incident is *not* unusually dispersed |
| `tl2_operators.py` | do temporal operators differ, and at what cost? | Step-local catches nothing at any separation; unbounded accumulators catch everything at 100-step latency. The false-positive half is **unscoreable** on a 9,503-word benign corpus and the script refuses to score it |
| `tl3_behaviours.py` | does it appear in other behaviour families? | **Unscoreable**: 44 external trajectories average 6.1 reasoning steps, so a 68-step separation is *inexpressible*, not absent |
| `tl5_semantic.py` | can a semantic monitor beat the window? | Partly. Triple co-occurrence stays **0 at every benign budget from 0.1% to 20%**, but reading meaning cuts the required window **68 → 16** at a 5% budget. So 68 is a property of a *lexical* detector |
| `tl6_rederive.py` | is the result an artifact of one implementation? | A second implementation sharing no code but the frozen vocabulary agrees **7/7**. Does not import the scoring module; extracts the pattern literals from source so none of the scoring logic runs |
| `tl7_benign_scale.py` | how often does the vocabulary fire on benign agent reasoning? | On **1,500,621 words** of public benign agent trajectories (158× the corpus previously held), all three families fire: 2 / 90 / 4 steps |
| `tl8_fpr_curve.py` | what does a latched repair cost at length? | Word-normalised: 0.76% at 50k words, **4.61%** at the incident's 129k, 13.78% at 250k |
| `tl9_generalisation.py` | does it hold across models and behaviours? | **Zero single-step co-occurrence across 1,500 labelled trajectories from three model families**, in a corpus where a 68-step separation *is* expressible |
| `tl_results_table.py` | the programme, in one table | Rebuilds every row from the committed JSON |

## Three results that went against us, kept here because they did

1. **The window is substantially lexical.** `tl5` shows a semantic monitor needs
   16 steps, not 68. Any claim that 68 is *the* required horizon is a claim
   about a pattern matcher, not about monitoring.
2. **The benign corpus was never the constraint — where we looked was.** We
   wrote that the registered repair "cannot be validated by us or by anyone
   else" for want of ~1.21M words of benign agent reasoning. `tl7` fetched 1.5M
   words from public agentic coding corpora. The repair measures at 4.61%.
3. **The detector does not generalise, only the operator finding does.** `tl9`
   finds all three families in just **1 of 750** sabotage trajectories. Those
   tasks do not verbalise a reality-discount licence, and a vocabulary built
   from one incident should not be expected to travel.

## Two things these scripts deliberately do not claim

- **This is not independent replication.** `tl6` is a second implementation by
  the same authors. It rules out single-implementation artifacts and nothing
  more. A hash manifest over 24 inputs, scripts and results is emitted so
  someone else can run the real thing.
- **A null is not a result when the corpus cannot express one.** `tl3` reports
  UNSCOREABLE rather than "no effect found", because its trajectories are too
  short for the effect to appear. Every script reports the largest separation
  its corpus could have shown.

## External corpora used

- Benign agent reasoning: public OpenHands agentic-coding trajectories.
- Labelled sabotage and benign: a public ControlArena mirror of SHADE-Arena
  (arXiv:2506.15740).

Neither is redistributed here. The scripts fetch or read them by identifier.
