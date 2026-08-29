"""SupplyNet supply chain agents.

Four specialists behind an orchestrator:

    Ingest      normalise a raw telemetry event into a shipment fact
    Disruption  decide whether an event threatens a delivery
    Reroute     propose alternatives when it does
    Notify      draft the message to the affected party

The shape of this project differs from the request/response agents
elsewhere in the portfolio: events arrive continuously on a Kinesis stream
rather than being asked for. Ingest and Disruption run per-record off the
stream, and only a disruption that clears a severity threshold escalates to
Reroute and Notify. That fan-in/fan-out is the point -- most events are
uneventful and must cost nothing to process.

Because events arrive unattended, the constraint here is different too: an
agent that invents a delay reason will page a human at 3am for nothing. Each
agent must ground its judgement in the event payload and say when the signal
is too weak to act on.
"""

from __future__ import annotations

from typing import Any

from src.common import MODEL_FAST, MODEL_STANDARD, BaseAgent

DISCLAIMER = (
    "Generated from the supplied telemetry. Verify against the carrier "
    "system of record before acting."
)


class IngestAgent(BaseAgent):
    """Normalise a raw carrier or sensor event into a structured fact."""

    NAME = "ingest"
    MODEL = MODEL_FAST
    SYSTEM_PROMPT = (
        "You normalise raw supply chain telemetry into a structured fact.\n"
        "Carriers, ports and IoT sensors all use different field names and "
        "units. Map what you are given onto the schema below.\n"
        "Do not infer a value that is absent -- leave it null and name it in "
        "unmapped_fields. A guessed ETA is worse than a missing one.\n"
        "Respond with JSON only:\n"
        '{"shipment_id": "...", "event_type": "departure|arrival|delay|'
        'exception|position|customs|unknown",\n'
        ' "location": "...", "timestamp": "ISO8601 or null",\n'
        ' "eta": "ISO8601 or null", "carrier": "...",\n'
        ' "raw_signal": "the phrase this was derived from",\n'
        ' "unmapped_fields": ["fields present but not understood"],\n'
        ' "confidence": "high|medium|low"}'
    )

    def handle(self, event: dict[str, Any] | str) -> dict[str, Any]:
        import json

        payload = event if isinstance(event, str) else json.dumps(event, indent=1)
        result = self.invoke_json("Raw event:\n%s" % payload)
        result["disclaimer"] = DISCLAIMER
        return result


class DisruptionAgent(BaseAgent):
    """Decide whether an event actually threatens a delivery."""

    NAME = "disruption"
    MODEL = MODEL_STANDARD
    SYSTEM_PROMPT = (
        "You assess whether a supply chain event threatens a delivery "
        "commitment.\n"
        "Most events are routine. Say so when they are: a false alarm costs "
        "an operator's attention, and repeated false alarms cost their trust "
        "in the system.\n"
        "Judge only from the event and any context supplied. If the signal is "
        "too weak to call, return severity none and say what you would need.\n"
        "Respond with JSON only:\n"
        '{"is_disruption": true,\n'
        ' "severity": "critical|high|medium|low|none",\n'
        ' "delay_estimate_hours": 0,\n'
        ' "affected_commitments": ["..."],\n'
        ' "reasoning": "one or two sentences grounded in the event",\n'
        ' "needed_to_confirm": ["what would raise or lower this"]}'
    )

    def handle(self, event: dict[str, Any], context: str = "") -> dict[str, Any]:
        import json

        prompt = "Event:\n%s" % json.dumps(event, indent=1)
        if context:
            prompt += "\n\nContext:\n%s" % context
        result = self.invoke_json(prompt)
        result["disclaimer"] = DISCLAIMER
        return result


class RerouteAgent(BaseAgent):
    """Propose alternative routings for a disrupted shipment."""

    NAME = "reroute"
    MODEL = MODEL_STANDARD
    SYSTEM_PROMPT = (
        "You propose alternative routings for a disrupted shipment.\n"
        "Work only from the options supplied. Do not invent carriers, lanes "
        "or transit times -- if the available options cannot recover the "
        "commitment, say that plainly rather than proposing something that "
        "does not exist.\n"
        "Give the trade-off for each option: what it costs and what it saves.\n"
        "Respond with JSON only:\n"
        '{"recommended": "option id or null",\n'
        ' "options": [{"id": "...", "route": "...",\n'
        '              "added_cost": "...", "time_saved_hours": 0,\n'
        '              "tradeoff": "...", "feasible": true}],\n'
        ' "commitment_recoverable": true,\n'
        ' "rationale": "why the recommendation, in one or two sentences"}'
    )

    def handle(
        self,
        shipment: dict[str, Any],
        disruption: dict[str, Any] | None = None,
        options: list[dict[str, Any]] | None = None,
    ) -> dict[str, Any]:
        import json

        parts = ["Shipment:\n%s" % json.dumps(shipment, indent=1)]
        if disruption:
            parts.append("Disruption:\n%s" % json.dumps(disruption, indent=1))
        parts.append(
            "Available options:\n%s" % json.dumps(options or [], indent=1)
            if options
            else "Available options: none supplied"
        )
        result = self.invoke_json("\n\n".join(parts), max_tokens=3000)
        result["disclaimer"] = DISCLAIMER
        return result


class NotifyAgent(BaseAgent):
    """Draft the notification to the affected party."""

    NAME = "notify"
    MODEL = MODEL_STANDARD
    SYSTEM_PROMPT = (
        "You draft supply chain notifications for a human to send.\n"
        "Lead with what changed and what it means for the recipient. State "
        "the new commitment if there is one, and say plainly when there is "
        "not -- a vague reassurance is worse than an honest delay.\n"
        "Include only facts from the supplied analysis. Keep it short: an "
        "operations inbox is not a place for prose.\n"
        "Respond with JSON only:\n"
        '{"audience": "customer|carrier|internal",\n'
        ' "urgency": "immediate|today|routine",\n'
        ' "subject": "...", "body": "...",\n'
        ' "facts_used": ["each claim in the message and its source"],\n'
        ' "requires_human_approval": true}'
    )

    def handle(
        self,
        disruption: dict[str, Any],
        reroute: dict[str, Any] | None = None,
        audience: str = "customer",
    ) -> dict[str, Any]:
        import json

        parts = ["Audience: %s" % audience,
                 "Disruption:\n%s" % json.dumps(disruption, indent=1)]
        if reroute:
            parts.append("Reroute analysis:\n%s" % json.dumps(reroute, indent=1))
        result = self.invoke_json("\n\n".join(parts), max_tokens=2500)
        result["disclaimer"] = DISCLAIMER
        return result


class OrchestratorAgent(BaseAgent):
    """Route an inbound request to the right specialist."""

    NAME = "orchestrator"
    MODEL = MODEL_FAST
    SYSTEM_PROMPT = (
        "You route supply chain requests to one specialist agent.\n"
        "Options:\n"
        "  ingest     - normalising a raw carrier or sensor event\n"
        "  disruption - judging whether an event threatens a delivery\n"
        "  reroute    - proposing alternative routings\n"
        "  notify     - drafting a message about a disruption\n"
        "Respond with JSON only:\n"
        '{"agent": "ingest|disruption|reroute|notify", "reason": "one sentence"}'
    )

    VALID = {"ingest", "disruption", "reroute", "notify"}

    def handle(self, request: str) -> dict[str, Any]:
        result = self.invoke_json("Request:\n%s" % request)
        if result.get("agent") not in self.VALID:
            # Ingest is the safe default: it is the only agent that accepts a
            # raw event without prior analysis.
            result = {
                "agent": "ingest",
                "reason": "router returned an unknown agent; defaulting to ingest",
            }
        return result


AGENTS: dict[str, type[BaseAgent]] = {
    "ingest": IngestAgent,
    "disruption": DisruptionAgent,
    "reroute": RerouteAgent,
    "notify": NotifyAgent,
    "orchestrator": OrchestratorAgent,
}

__all__ = ["AGENTS", "DisruptionAgent", "IngestAgent", "NotifyAgent",
           "OrchestratorAgent", "RerouteAgent"]
