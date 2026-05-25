from types import SimpleNamespace
from datetime import datetime

import pytest

from app.services.event_pipeline import EventPipeline
from app.ingestion import events_collector

def test_event_pipeline_sends_transformed_event(monkeypatch):
    """Verify that EventPipeline transforms and sends raw Kubernetes events."""

    raw_event = SimpleNamespace(
        type="Normal",
        reason="TestReason",
        message="Test event message",
        metadata=SimpleNamespace(namespace="default"),
        involved_object=SimpleNamespace(kind="Pod", name="mypod"),
        last_timestamp=datetime(2025, 1, 1, 12, 0, 0),
    )

    def fake_stream_raw_events(namespace=None):
        assert namespace == "demo"
        yield raw_event

    class DummyProducer:
        def __init__(self):
            self.sent = []

        def send_event(self, topic, event):
            self.sent.append((topic, event))

        def flush(self):
            pass

        def close(self):
            pass

    dummy_producer = DummyProducer()
    monkeypatch.setattr("app.services.event_pipeline.stream_raw_events", fake_stream_raw_events)
    monkeypatch.setattr("app.services.event_pipeline.KafkaProducerService", lambda: dummy_producer)

    pipeline = EventPipeline()
    pipeline.run(namespace="demo")

    assert len(dummy_producer.sent) == 1
    topic, event_payload = dummy_producer.sent[0]
    assert topic == "kube-events"
    assert event_payload["object_name"] == "mypod"
    assert event_payload["namespace"] == "default"


    