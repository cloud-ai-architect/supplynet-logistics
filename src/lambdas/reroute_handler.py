"""Lambda handler for the Reroute stage."""

from __future__ import annotations

from src.agents.supplynet import RerouteAgent
from src.lambdas._base import run_stage


def handler(event: dict, context: object) -> dict:
    return run_stage(
        event,
        required=["shipment"],
        fn=lambda d: RerouteAgent().run(
            d["shipment"], d.get("disruption"), d.get("options")
        ),
    )
