from kafka import KafkaProducer
import json
import logging
import os

logger = logging.getLogger(__name__)

class KafkaProducerService:
    """Service responsible for sending messages to Kafka"""

    def __init__(self, bootstrap_servers: str = None):
        self.bootstrap_servers = bootstrap_servers or os.getenv(
            "KAFKA_BOOTSTRAP_SERVERS", "localhost:9092"
        )

        self.producer = KafkaProducer(
            bootstrap_servers=self.bootstrap_servers,
            value_serializer=lambda v: json.dumps(v).encode("utf-8"),
            acks="all",
            retries=5,
            enable_idempotence=True,
            linger_ms=10,
            batch_size=16384,
        )

    def send_event(self, topic: str, event: dict):
        try:
            future = self.producer.send(
                topic,
                key=event.get("object_name", "").encode("utf-8"),
                value=event
            )

            future.add_callback(self.on_send_success)
            future.add_errback(self.on_send_error)

        except Exception as e:
            logger.error(f"Failed to send event to Kafka: {e}", exc_info=True)

    def on_send_success(self, record_metadata):
        logger.info(
            f"Sent to {record_metadata.topic} "
            f"partition={record_metadata.partition} "
            f"offset={record_metadata.offset}"
        )

    def on_send_error(self, exc):
        logger.error(f"Kafka send failed: {exc}", exc_info=True)

    def flush(self):
        self.producer.flush()

    def close(self):
        self.producer.flush()
        self.producer.close()