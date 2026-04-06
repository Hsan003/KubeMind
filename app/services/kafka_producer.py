from kafka import KafkaProducer
import json
import logging

logger = logging.getLogger(__name__)

class KafkaProducerService:
    """Service responsible for sending messages to Kafka"""

    def __init__(self, bootstrap_servers: str = "localhost:9092"):
        self.producer = KafkaProducer(
            bootstrap_servers=bootstrap_servers,
            value_serializer=lambda v: json.dumps(v).encode("utf-8")
        )

    def send_event(self, topic: str, event: dict):
        """Send an event to a Kafka topic"""
        try:
            self.producer.send(topic, event)
            logger.info(f"Event sent to Kafka topic={topic}")
        except Exception as e:
            logger.error(f"Failed to send event to Kafka: {e}", exc_info=True)

    def flush(self):
        self.producer.flush()