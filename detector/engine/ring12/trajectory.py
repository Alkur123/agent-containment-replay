"""Minimal Action/Step shim so the frozen detector runs standalone.

`rationalization.py` in this directory is a **byte-identical copy** of the file
under test in the author's private repository (sha256 recorded in the
pre-registration). It imports `Action` and `Step` from this module. Rather than
edit the detector to remove that import — which would break byte-identity and
therefore break the point of publishing it — this file supplies the two
dataclasses it needs and nothing else.

The full versions carry embeddings, timestamps and serialization helpers the
detector never touches.
"""

from __future__ import annotations

from dataclasses import dataclass, field
from typing import Optional


@dataclass
class Action:
    """One tool call the agent is about to make."""
    type: str = "tool_call"
    name: str = ""
    args: dict = field(default_factory=dict)
    class_: str = "READ"        # READ WRITE NETWORK COMPUTE COMMUNICATE SYSTEM
    raw: str = ""


@dataclass
class Step:
    """One agent step: thought -> action -> observation."""
    index: int = 0
    thought: str = ""
    action: Optional[Action] = None
    observation: str = ""
