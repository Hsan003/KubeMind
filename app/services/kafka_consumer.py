from kafka import KafkaConsumer
import json


def create_consumer() -> KafkaConsumer:
    return KafkaConsumer(
        "kube-events",
        bootstrap_servers="localhost:9092",
        auto_offset_reset="latest",
        group_id="debug",
        value_deserializer=lambda m: json.loads(m.decode("utf-8")),
    )


def run_consumer() -> None:
    consumer = create_consumer()
    print("👂 Listening to Kafka...")
    for msg in consumer:
        print(msg.value)


if __name__ == "__main__":
    run_consumer()