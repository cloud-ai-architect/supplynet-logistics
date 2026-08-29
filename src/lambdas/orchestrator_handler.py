"""Lambda handler for the Orchestrator."""

from __future__ import annotations

from src.agents.supplynet import AGENTS, OrchestratorAgent
from src.lambdas._base import run_stage

DISPATCH = {
    "ingest": lambda d: (d.get("event") or d["request"],),
    "disruption": lambda d: (d.get("event") or {"raw": d["request"]}, d.get("context", "")),
    "reroute": lambda d: (d.get("shipment") or {}, d.get("disruption"), d.get("options")),
    "notify": lambda d: (d.get("disruption") or {}, d.get("reroute"), d.get("audience", "customer")),
}


def _route_and_run(data: dict) -> dict:
    decision = OrchestratorAgent().run(data["request"])
    name = decision["agent"]
    return {
        "routed_to": name,
        "routing_reason": decision.get("reason"),
        "output": AGENTS[name]().run(*DISPATCH[name](data)),
    }


def handler(event: dict, context: object) -> dict:
    return run_stage(event, required=["request"], fn=_route_and_run)
