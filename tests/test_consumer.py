from kafka import KafkaConsumer
import json

consumer = KafkaConsumer(
    "kube-events",
    bootstrap_servers="localhost:9092",
    value_deserializer=lambda m: json.loads(m.decode("utf-8")),
    auto_offset_reset="earliest"
)

print("👂 Listening to Kafka...")

for msg in consumer:
    print("📥 RECEIVED:", msg.value)