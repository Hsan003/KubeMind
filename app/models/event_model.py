from pydantic import BaseModel

class KubernetesEvent(BaseModel):
    type: str
    reason: str
    message: str
    namespace: str
    object_kind: str
    object_name: str
    timestamp: str