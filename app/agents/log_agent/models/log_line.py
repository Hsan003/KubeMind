from dataclasses import dataclass, field
@dataclass

class LogLine:
    timestamp_ns: str          # Unix nanoseconds (Loki native)
    timestamp_iso: str         # Human-readable ISO-8601 UTC
    message: str
    stream_labels: dict[str, str]



