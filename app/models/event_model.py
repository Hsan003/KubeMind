from typing import Optional
from pydantic import BaseModel

class KubernetesEvent(BaseModel):
    """
    Standardized model for a Kubernetes event, used for Kafka and downstream processing.
    """
    type: str  # Event type (e.g., Normal, Warning)
    reason: str  # Reason for the event
    message: Optional[str]  # Event message
    namespace: str  # Namespace where the event occurred
    object_kind: str  # Kind of the involved object (e.g., Pod, Node)
    object_name: str  # Name of the involved object
    timestamp: Optional[str]  # timestamp of the event