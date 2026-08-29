"""Lambda handler for the Notify stage."""

from __future__ import annotations

from typing import Any

from src.agents.supplynet import NotifyAgent
from src.lambdas._base import run_stage


def handler(event: dict[str, Any], context: object) -> dict[str, Any]:
    return run_stage(
        event,
        required=["disruption"],
        fn=lambda d: NotifyAgent().run(
            d["disruption"], d.get("reroute"), d.get("audience", "customer")
        ),
    )
