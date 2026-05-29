
from dataclasses import dataclass, field
@dataclass

class QueryStats:
    lines_returned: int
    streams_count: int
    bytes_processed: str
    exec_time_ms: int