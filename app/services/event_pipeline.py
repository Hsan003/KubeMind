
"""
EventPipeline: Orchestrates the flow of Kubernetes events from the cluster to Kafka.
1. Collects raw K8s events using the ingestion module.
2. Transforms them into a standard model.
3. Pushes them to Kafka for downstream processing.
"""
from app.ingestion.events_collector import stream_raw_events
from app.services.event_transformer import transform_event
from app.services.kafka_producer import KafkaProducerService

class EventPipeline:
    def __init__(self):
        # Initialize Kafka producer service
        self.kafka = KafkaProducerService()

    def run(self, namespace=None):
        """
        Collects events from Kubernetes, transforms, and pushes to Kafka.
        Args:
            namespace (str, optional): If provided, only stream events from this namespace.
        """
        for raw_event in stream_raw_events(namespace):
            # Transform raw K8s event object to standard model
            event = transform_event(raw_event)
            # Push only warning event to Kafka topic 'kube-events'
            if event.type == "Warning":
                self.kafka.send_event("kube-events", event.model_dump())