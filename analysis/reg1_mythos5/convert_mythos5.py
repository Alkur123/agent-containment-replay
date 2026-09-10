"""Convert anthropics/mythos-5-incident-transcript to the registered step schema.

Implements SEGMENTATION_SPEC.md against the transcript's ACTUAL format, which
that spec could not know when it was committed on 2026-08-02. Every rule below
cites the section it comes from. Deviations are declared, not silent (spec 10).

TRANSCRIPT FORMAT, as observed structurally (field names and counts only; no
natural-language content was read before this file was committed):

    transcript.jsonl, 2065 lines
      1 x record="metadata"  (title/subtitle/notice/about/modifications)
      2064 x record="message" with index, role, type, timestamp
        type="ToolMessage" 1361  -> tool_name, tool_call (dict|None), tool_result
        type="TextMessage"  703  -> content   (role: Assistant 700, Human 2, System 1)
      tool_name in {terminal, view_tool, create_tool, str_replace_tool}
      13 ToolMessages carry tool_call=None plus a tool_call_raw string.

MAPPING

  spec 2  step = one action emitted by the model.
          Every ToolMessage is exactly one step, in transcript order, including
          the 13 whose tool_call failed to parse -- the model still emitted the
          call. tool_result is an observation and is never a step. The System
          turn and the 2 Human turns are scaffold and are never steps.
          Trailing model text after the final action becomes one last step with
          action.name="" and class_="READ".

  spec 3  thought = all model-authored text since the previous action.
          Assistant TextMessage content is concatenated in transcript order with
          a single newline. This transcript carries its reasoning channel INLINE
          as <thinking> blocks inside that same content field rather than as a
          separate channel, so including content whole is what "concatenate both
          in transcript order" reduces to here. Human/System turns are excluded
          (not model-authored). tool_result is excluded. Redaction markers are
          copied through verbatim and never reconstructed.

  spec 4  action.name = tool_name, lowercased and stripped, unchanged otherwise.
          NOT normalised toward the detector's vocabulary. args = tool_call when
          it is a dict, else {} -- tool_call_raw is an unparsed string, not the
          "structured arguments" the spec admits.

  spec 5  class_. The transcript supplies NO action-category field: tool_name is
          a name (spec 4), not a category. Spec 5's closing rule therefore
          applies verbatim -- "If the transcript supplies no categories at all,
          every step is READ." That is the PRIMARY arm and it biases against the
          detector, since READ never receives the 1.25 consequential multiplier.
          --class-from-toolname runs the declared SENSITIVITY arm instead,
          applying spec 5's substring table to tool_name. It can only raise
          scores, never lower them, so it cannot rescue a passing result and can
          only explain a failing one.

  spec 6  is_upload. Judged from the action and its arguments, never from the
          reasoning. Qualifying = the action transmits the package artifact to
          the package index. Retries exist, so the pre-decided tie-break applies:
          "label the first one that succeeded." Determined from the returned
          status in tool_result, which is an observation and not reasoning.

  spec 7  index = zero-based position in the emitted array. Nothing is reordered,
          deduplicated, merged or dropped.
"""

from __future__ import annotations

import argparse
import json
import pathlib

# spec 5 substring table, used ONLY by the declared sensitivity arm.
CLASS_TABLE = [
    (("network", "http", "request", "fetch", "upload", "download"), "NETWORK"),
    (("write", "create", "put", "save", "publish"), "WRITE"),
    (("exec", "run", "shell", "command", "compute"), "COMPUTE"),
    (("mail", "message", "send", "notify", "communicate"), "COMMUNICATE"),
    (("system", "admin", "privilege", "sudo"), "SYSTEM"),
]

# spec 6. The upload step is identified by argument text, then narrowed to the
# first that succeeded. Both halves are recorded so the label is auditable.
UPLOAD_ARG_MARKERS = ("upload.py", "upload2.py", "upload_test.py", ":action")


def classify(tool_name):
    low = (tool_name or "").lower()
    for needles, cls in CLASS_TABLE:
        if any(n in low for n in needles):
            return cls
    return "READ"


def load(path):
    return [json.loads(l) for l in path.read_text(encoding="utf-8").splitlines() if l.strip()]


def label_upload(steps):
    """spec 6: qualifying actions, then the first that succeeded."""
    cands = []
    for s in steps:
        args = json.dumps(s["action"]["args"]).lower()
        if not any(m in args for m in UPLOAD_ARG_MARKERS):
            continue
        if "curl" in args and "upload.pypi.org" in args:
            continue  # reachability probe: transmits no artifact
        res = s.get("_tool_result", "")
        ok = ("status: 200" in res) or ("status: 201" in res)
        head = s["action"]["args"].get("text") or s["action"]["args"].get("path") or ""
        cands.append({"index": s["index"], "succeeded": ok, "arg_head": head[:90]})
    succeeded = [c for c in cands if c["succeeded"]]
    if succeeded:
        return succeeded[0]["index"], cands
    return (cands[0]["index"] if cands else None), cands


def convert(records, class_from_toolname=False):
    msgs = [r for r in records if r.get("record") == "message"]
    msgs.sort(key=lambda r: r.get("index", 0))

    steps = []
    pending = []
    n_unparsed = 0

    for r in msgs:
        typ, role = r.get("type"), r.get("role")
        if typ == "TextMessage":
            if role == "Assistant":                        # spec 3, model-authored only
                c = r.get("content")
                if c:
                    pending.append(c)
            continue
        if typ != "ToolMessage":
            continue

        tc = r.get("tool_call")
        if not isinstance(tc, dict):
            tc = {}                                        # spec 4
            n_unparsed += 1
        name = (r.get("tool_name") or "").strip().lower()  # spec 4
        steps.append({
            "index": len(steps),                           # spec 7
            "thought": "\n".join(pending),                 # spec 3
            "action": {"name": name, "args": tc,
                       "class_": classify(name) if class_from_toolname else "READ"},
            "is_upload": False,
            "_tool_result": r.get("tool_result") or "",
        })
        pending = []

    if pending:                                            # spec 2, trailing text
        steps.append({"index": len(steps), "thought": "\n".join(pending),
                      "action": {"name": "", "args": {}, "class_": "READ"},
                      "is_upload": False, "_tool_result": ""})

    upload_idx, cands = label_upload(steps)
    if upload_idx is not None:
        steps[upload_idx]["is_upload"] = True

    meta = {
        "n_steps": len(steps),
        "n_tool_messages": sum(1 for r in msgs if r.get("type") == "ToolMessage"),
        "n_text_messages_assistant": sum(1 for r in msgs
                                         if r.get("type") == "TextMessage"
                                         and r.get("role") == "Assistant"),
        "n_scaffold_turns_excluded": sum(1 for r in msgs
                                         if r.get("type") == "TextMessage"
                                         and r.get("role") in ("Human", "System")),
        "n_unparsed_tool_calls_kept_as_steps": n_unparsed,
        "upload_index": upload_idx,
        "upload_candidates": cands,
        "class_arm": "toolname_sensitivity" if class_from_toolname else "all_READ_primary",
    }
    for s in steps:
        s.pop("_tool_result", None)
    return steps, meta


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--jsonl", type=pathlib.Path, required=True)
    ap.add_argument("--out", type=pathlib.Path, required=True)
    ap.add_argument("--meta", type=pathlib.Path)
    ap.add_argument("--class-from-toolname", action="store_true",
                    help="declared SENSITIVITY arm (spec 5); not the registered primary")
    a = ap.parse_args()

    steps, meta = convert(load(a.jsonl), a.class_from_toolname)
    a.out.write_text(json.dumps(steps, indent=1), encoding="utf-8")

    # spec 8, the void condition, evaluated on the converted JSON BEFORE scoring.
    if meta["upload_index"] is not None:
        upto = [s for s in steps if s["index"] <= meta["upload_index"]]
    else:
        upto = steps
    nonempty = [s for s in upto
                if s["thought"].strip() and s["thought"].replace("[redacted]", "").strip()]
    meta["void_check"] = {
        "steps_at_or_before_upload": len(upto),
        "nonempty_thoughts_at_or_before_upload": len(nonempty),
        "void": len(nonempty) == 0,
    }
    print(json.dumps(meta, indent=1))
    if a.meta:
        a.meta.write_text(json.dumps(meta, indent=1), encoding="utf-8")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
