# app/services/event_pipeline.py

from app.ingestion.events_collector import stream_raw_events
from app.services.event_transformer import transform_event
from app.services.kafka_producer import KafkaProducerService

class EventPipeline:
    def __init__(self):
        self.kafka = KafkaProducerService()

    def run(self, namespace=None):
        for raw_event in stream_raw_events(namespace):
            event = transform_event(raw_event)
            self.kafka.send_event("kube-events", event.dict())