from datetime import datetime

from app.services.event_transformer import transform_event


class DummyMeta:
    def __init__(self, namespace=None, creation_timestamp=None):
        self.namespace = namespace
        self.creation_timestamp = creation_timestamp


class DummyObjectRef:
    def __init__(self, kind=None, name=None, namespace=None):
        self.kind = kind
        self.name = name
        self.namespace = namespace


class DummyEvent:
    def __init__(self):
        self.type = "Warning"
        self.reason = "FailedScheduling"
        self.message = None
        self.metadata = DummyMeta(namespace="default", creation_timestamp=datetime.utcnow())
        self.involved_object = DummyObjectRef(kind="Pod", name="my-pod", namespace="default")
        self.last_timestamp = None
        self.event_time = None


def test_transform_event_allows_missing_message_and_timestamp() -> None:
    event = transform_event(DummyEvent())

    assert event.type == "Warning"
    assert event.reason == "FailedScheduling"
    assert event.message is None
    assert event.timestamp is not None
    assert event.namespace == "default"
    assert event.object_kind == "Pod"
    assert event.object_name == "my-pod"
