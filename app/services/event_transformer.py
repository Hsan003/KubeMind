from app.models.event_model import KubernetesEvent

def transform_event(obj) -> KubernetesEvent:
    event_data = {
        "type": obj.type,
        "reason": obj.reason,
        "message": obj.message,
        "namespace": obj.metadata.namespace,
        "object_kind": obj.involved_object.kind,
        "object_name": obj.involved_object.name,
        "timestamp": obj.last_timestamp.isoformat() if obj.last_timestamp else None
    }

    return KubernetesEvent(**event_data)