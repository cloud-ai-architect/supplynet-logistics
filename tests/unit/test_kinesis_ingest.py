"""Tests for Kinesis record handling in the ingest stage.

The stream path has different failure semantics from the HTTP path: one
bad record must not fail the batch, because a failed batch is retried
whole and blocks its shard until the records age out.
"""

from __future__ import annotations

import base64
import json

from src.lambdas.ingest_handler import _decode, _is_kinesis


def kinesis_record(payload, seq="1"):
    raw = payload if isinstance(payload, str) else json.dumps(payload)
    return {
        "eventSource": "aws:kinesis",
        "kinesis": {
            "data": base64.b64encode(raw.encode()).decode(),
            "sequenceNumber": seq,
        },
    }


class TestSourceDetection:
    def test_kinesis_batch_recognised(self):
        assert _is_kinesis({"Records": [kinesis_record({"a": 1})]})

    def test_http_request_is_not_kinesis(self):
        assert not _is_kinesis({"event": {"a": 1}})

    def test_empty_records_is_not_kinesis(self):
        assert not _is_kinesis({"Records": []})

    def test_other_event_source_is_not_kinesis(self):
        rec = kinesis_record({"a": 1})
        rec["eventSource"] = "aws:sqs"
        assert not _is_kinesis({"Records": [rec]})

    def test_non_dict_is_not_kinesis(self):
        assert not _is_kinesis({})


class TestDecode:
    def test_json_payload_returns_dict(self):
        out = _decode(kinesis_record({"shipment": "S1", "scan": "DEPARTED"}))
        assert out["shipment"] == "S1"

    def test_non_json_payload_returns_text(self):
        """Not every producer sends JSON; the ingest agent reads prose too,
        so a decode failure must not raise."""
        out = _decode(kinesis_record("SHP-1 delayed at Rotterdam"))
        assert isinstance(out, str)
        assert "Rotterdam" in out

    def test_empty_payload_does_not_raise(self):
        assert _decode(kinesis_record("")) == ""

    def test_unicode_survives_the_round_trip(self):
        out = _decode(kinesis_record({"loc": "Gothenburg"}))
        assert out["loc"] == "Gothenburg"
