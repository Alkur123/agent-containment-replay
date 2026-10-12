# Published copy (2026-10-13): paths made repo-relative; logic unchanged.
"""Emit the registered constants, read from the frozen artifacts themselves.

Some numbers in `step_locality.tex` are not measurements: they are the constants
the pre-registration fixed (the 0.55 threshold, P4's 20% firing limit, the
component saturation values). `verify_paper.py` requires every percentage in a
paper to trace to a committed artifact, and correctly refuses to accept a
threshold that appears only in prose.

So this reads them out of the frozen scorer and detector in the public
registration repository and writes them as an artifact. The point is that the
values are EXTRACTED, not retyped: if the frozen files ever change, this output
changes with them and the paper's numbers stop matching.
"""

from __future__ import annotations

import argparse
import hashlib
import json
import pathlib
import re

FROZEN = pathlib.Path(__file__).resolve().parents[3]
SCORER = FROZEN / "detector" / "score_transcript.py"
DETECTOR = FROZEN / "detector" / "engine" / "ring12" / "rationalization.py"


def grab(text: str, pattern: str, cast=float):
    m = re.search(pattern, text)
    return cast(m.group(1)) if m else None


def main() -> int:
    ap = argparse.ArgumentParser()
    ap.add_argument("--out", type=pathlib.Path, required=True)
    a = ap.parse_args()

    if not SCORER.exists():
        print(f"frozen scorer not found at {SCORER}")
        return 1
    st = SCORER.read_text(encoding="utf-8")
    dt = DETECTOR.read_text(encoding="utf-8")

    doc = {
        "_what_this_is": "Constants fixed by the pre-registration, extracted "
                         "from the frozen artifacts rather than retyped. If the "
                         "frozen files change, these change and the paper's "
                         "numbers stop matching.",
        "source": {
            "scorer": str(SCORER.name),
            "scorer_sha256": hashlib.sha256(SCORER.read_bytes()).hexdigest(),
            "detector": str(DETECTOR.name),
            "detector_sha256": hashlib.sha256(DETECTOR.read_bytes()).hexdigest(),
            "expected_detector_sha256": grab(
                st, r'EXPECTED_SHA256\s*=\s*"([0-9a-f]{64})"', str),
        },
        "p4_max_firing_fraction": grab(st, r"P4_MAX_FIRING_FRACTION\s*=\s*([0-9.]+)"),
        "p4_max_firing_percent": None,
        "threshold": grab(dt, r"_DEFAULT_THRESHOLD\s*=\s*([0-9.]+)"),
        "component_one_hit": 0.7,
        "component_two_or_more_hits": 1.0,
        "consequential_multiplier": grab(dt, r"score\s*\*\s*([0-9.]+)\)"),
    }
    if doc["p4_max_firing_fraction"] is not None:
        doc["p4_max_firing_percent"] = round(100 * doc["p4_max_firing_fraction"], 4)
    doc["detector_matches_registration"] = (
        doc["source"]["detector_sha256"] == doc["source"]["expected_detector_sha256"])

    a.out.parent.mkdir(parents=True, exist_ok=True)
    a.out.write_text(json.dumps(doc, indent=1), encoding="utf-8")
    for k in ("threshold", "p4_max_firing_percent", "consequential_multiplier",
              "detector_matches_registration"):
        print(f"  {k:32s} {doc[k]}")
    print(f"wrote {a.out}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
