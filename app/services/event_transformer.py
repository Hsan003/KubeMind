from app.models.event_model import KubernetesEvent

def transform_event(obj) -> KubernetesEvent:
    timestamp = None
    if getattr(obj, "last_timestamp", None):
        timestamp = obj.last_timestamp.isoformat()
    elif getattr(obj, "event_time", None):
        timestamp = obj.event_time.isoformat()
    elif getattr(obj.metadata, "creation_timestamp", None):
        timestamp = obj.metadata.creation_timestamp.isoformat()

    event_data = {
        "type": obj.type,
        "reason": obj.reason,
        "message": obj.message,
        "namespace": getattr(obj.metadata, "namespace", None) or getattr(obj.involved_object, "namespace", None),
        "object_kind": obj.involved_object.kind,
        "object_name": obj.involved_object.name,
        "timestamp": timestamp,
    }

    return KubernetesEvent(**event_data)