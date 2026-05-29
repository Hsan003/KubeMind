from dataclasses import dataclass, field
from app.agents.log_agent.models.log_line import LogLine
@dataclass

class LogStream:
    labels: dict[str, str]
    lines: list[LogLine]