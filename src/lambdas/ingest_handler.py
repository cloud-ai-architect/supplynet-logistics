"""Lambda handler for the Ingest stage.

Serves two callers with different contracts:

  - Kinesis, delivering batches of raw telemetry. Records are processed
    individually and failures are reported per record, so one malformed
    event does not fail the whole batch and stall the shard behind it.
  - The HTTP API, for normalising a single event on demand.
"""

from __future__ import annotations

import base64
import json
import os
from typing import Any

import boto3

from src.agents.supplynet import DisruptionAgent, IngestAgent
from src.lambdas._base import run_stage

REGION = os.environ.get("AWS_REGION", "ap-south-1")
EVENTS_TABLE = os.environ.get("ORDERS_TABLE", "")

# Only disruptions at or above this severity are worth escalating. Most
# telemetry is routine, and paging an operator for a routine scan is how a
# system trains people to ignore it.
ESCALATE_AT = {"critical", "high"}


def _is_kinesis(event: dict) -> bool:
    records = event.get("Records") or []
    return bool(records) and records[0].get("eventSource") == "aws:kinesis"


def _decode(record: dict) -> Any:
    raw = base64.b64decode(record["kinesis"]["data"]).decode("utf-8")
    try:
        return json.loads(raw)
    except json.JSONDecodeError:
        # Not every producer sends JSON; the ingest agent can read prose.
        return raw


def _process_one(payload: Any) -> dict[str, Any]:
    """Normalise, then assess. Assessment only runs if normalisation worked."""
    fact = IngestAgent().run(payload)

    assessment = None
    if fact.get("confidence") != "low":
        assessment = DisruptionAgent().run(fact)

    escalate = bool(
        assessment
        and assessment.get("is_disruption")
        and assessment.get("severity") in ESCALATE_AT
    )

    return {"fact": fact, "assessment": assessment, "escalate": escalate}


def _persist(result: dict[str, Any]) -> None:
    if not EVENTS_TABLE:
        return
    fact = result["fact"]
    shipment = fact.get("shipment_id")
    if not shipment:
        return

    # event_ts is the table's sort key. Fall back to ingestion time when the
    # source event carries no timestamp, so an undated event still lands
    # rather than overwriting the shipment's most recent record.
    import datetime

    event_ts = fact.get("timestamp") or datetime.datetime.now(
        datetime.timezone.utc
    ).strftime("%Y-%m-%dT%H:%M:%S.%fZ")

    item = {
        "order_id": {"S": str(shipment)},
        "event_ts": {"S": str(event_ts)},
        "event_type": {"S": str(fact.get("event_type", "unknown"))},
        "escalated": {"BOOL": bool(result.get("escalate"))},
        "payload": {"S": json.dumps(result)[:38000]},
    }
    boto3.client("dynamodb", region_name=REGION).put_item(
        TableName=EVENTS_TABLE, Item=item
    )


def handler(event: dict, context: object) -> dict:
    if _is_kinesis(event):
        # Per-record failure reporting: Kinesis retries only the records that
        # actually failed rather than the whole batch.
        failures = []
        escalated = 0

        for record in event.get("Records", []):
            try:
                result = _process_one(_decode(record))
                _persist(result)
                if result["escalate"]:
                    escalated += 1
            except Exception:  # noqa: BLE001 - one bad record must not stall the shard
                failures.append({"itemIdentifier": record["kinesis"]["sequenceNumber"]})

        print(json.dumps({
            "processed": len(event.get("Records", [])),
            "escalated": escalated,
            "failed": len(failures),
        }))
        return {"batchItemFailures": failures}

    return run_stage(
        event,
        required=["event"],
        fn=lambda d: _process_one(d["event"]),
    )
