"""Lambda handler for the Disruption stage."""

from __future__ import annotations

from src.agents.supplynet import DisruptionAgent
from src.lambdas._base import run_stage


def handler(event: dict, context: object) -> dict:
    return run_stage(
        event,
        required=["event"],
        fn=lambda d: DisruptionAgent().run(d["event"], d.get("context", "")),
    )
