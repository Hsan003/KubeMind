from kubernetes import client, config, watch
import json
from app.models.event_model import KubernetesEvent
from app.services.kafka_producer import KafkaProducerService

kafka_service = KafkaProducerService()

def stream_events(namespace=None):
    print("Setting up Kubernetes client...")
    try:
        print("Trying in-cluster config...")
        config.load_incluster_config()
    except:
        print("In-cluster config failed, trying kubeconfig...")
        config.load_kube_config()

    v1 = client.CoreV1Api()
    w = watch.Watch()

    print("Listening to events...")

    for event in w.stream(v1.list_namespace_event(namespace=namespace) if namespace else v1.list_event_for_all_namespaces()):
        obj = event["object"]

        event_data = {
            "type": obj.type,
            "reason": obj.reason,
            "message": obj.message,
            "namespace": obj.metadata.namespace,
            "object_kind": obj.involved_object.kind,
            "object_name": obj.involved_object.name,
            "timestamp": obj.last_timestamp.isoformat() if obj.last_timestamp else None
        }
        event = KubernetesEvent(**event_data)
        kafka_service.send_event("kube-events", event.dict())

if __name__ == "__main__":
    print("Starting events collector...")
    stream_events(namespace = "demo")