# KubeMind - Kubernetes AI Incident Analyzer

AI-powered incident analyzer for Kubernetes clusters with multi-agent analysis capabilities.

## Features

- **Multi-Agent Architecture**: Specialized agents for logs, metrics, events, and correlation analysis
- **Log Analysis**: Pattern-based error detection in pod logs with severity classification
- **Metrics Analysis**: Prometheus metrics monitoring for CPU, memory, and error rate anomalies
- **Events Monitoring**: Kubernetes API event tracking and analysis
- **Correlation Engine**: Aggregate findings from multiple sources to identify patterns
- **Root Cause Analysis**: Intelligent reasoning to determine underlying causes
- **Automated Reporting**: Generate detailed markdown incident reports
- **RESTful API**: FastAPI-based API for incident management
- **Kubernetes Native**: Designed for Kubernetes deployment with manifests included
- **Async Support**: Full async/await implementation for high performance
- **Type Safety**: Comprehensive type hints and Pydantic validation

## Project Structure

```
k8s-ai-incident-analyzer/
├── app/
│   ├── agents/                 # Specialized analysis agents
│   │   ├── base_agent.py       # Abstract base class for all agents
│   │   ├── log_agent/          # Log analysis agent
│   │   ├── metrics_agent/      # Metrics analysis agent
│   │   ├── events_agent/       # Kubernetes events agent
│   │   ├── correlation_agent/  # Finding correlation engine
│   │   ├── root_cause_agent/   # Root cause analysis engine
│   │   └── report_agent/       # Report generation agent
│   ├── api/                    # FastAPI routes and endpoints
│   ├── ingestion/              # Data ingestion from external sources
│   ├── models/                 # Pydantic data models
│   ├── services/               # Business logic (orchestrator)
│   ├── storage/                # Database configuration
│   ├── utils/                  # Utilities (logging, etc.)
│   └── main.py                 # FastAPI application entry point
├── config/                     # Application configuration
├── tests/                      # Test suite
├── docker/                     # Docker configuration
├── k8s/                        # Kubernetes manifests
├── requirements.txt            # Python dependencies
├── README.md                   # This file
├── .env.example                # Environment template
└── .gitignore                  # Git ignore rules
```

## Installation

### Prerequisites

- Python 3.11 or higher
- pip package manager
- Docker (optional, for containerized deployment)
- Kubernetes cluster (optional, for K8s deployment)

### Local Setup

1. Clone the repository:
```bash
cd /path/to/KubeMind
```

2. Create a virtual environment:
```bash
python3 -m venv venv
source venv/bin/activate  # On Windows: venv\Scripts\activate
```

3. Install dependencies:
```bash
pip install -r requirements.txt
```

4. Configure environment:
```bash
cp .env .env
# Edit .env with your configuration
```

## Running the Application

### Development Mode

Run with hot reload for development:
```bash
uvicorn app.main:app --reload --host 0.0.0.0 --port 8000
```

The API will be available at `http://localhost:8000`

Interactive API documentation: `http://localhost:8000/docs`

Alternative documentation: `http://localhost:8000/redoc`

### Production Mode

Run without hot reload:
```bash
uvicorn app.main:app --host 0.0.0.0 --port 8000 --workers 4
```

### Docker Deployment

Build Docker image:
```bash
docker build -f docker/Dockerfile -t k8s-ai-incident-analyzer:latest .
```

Run container:
```bash
docker run -p 8000:8000 \
  -e LOKI_URL=http://loki:3100 \
  -e PROMETHEUS_URL=http://prometheus:9090 \
  k8s-ai-incident-analyzer:latest
```

### Kubernetes Deployment

Deploy to Kubernetes cluster:
```bash
kubectl apply -f k8s/deployment.yaml
```

Check deployment status:
```bash
kubectl get deployments
kubectl get pods
kubectl logs -f deployment/k8s-ai-incident-analyzer
```

## API Endpoints

### Metrics Collector (V1)
- **POST** `/api/v1/metrics/collect` - Collect Prometheus metrics for a namespace/workload scope.

Example request:
```bash
curl -X POST http://localhost:8000/api/v1/metrics/collect \
  -H "Content-Type: application/json" \
  -d '{
    "namespace": "default",
    "workload_name": "demo-api",
    "lookback_minutes": 15,
    "step": "30s"
  }'
```

Response behavior:
- Returns normalized metric groups for CPU, memory, restart count, request rate, and error rate.
- Each metric has explicit status values: `success`, `empty`, or `error`.
- `empty` means Prometheus returned 200 but no matching time series.

### System
- **GET** `/health` - Health check with real Prometheus connectivity probe (`up` query).
- **GET** `/` - Root endpoint

### Prometheus metric assumptions
- CPU: `container_cpu_usage_seconds_total`
- Memory: `container_memory_working_set_bytes`
- Restarts: `kube_pod_container_status_restarts_total`
- Requests/error rates: `http_requests_total`

If your cluster uses different metric names or labels, update the query catalog in `app/ingestion/queries.py`.

## Code Writing Best Practices

### Class and Function Documentation

Every class and function should have comprehensive docstrings:

```python
class MyClass:
    """One-line summary of the class.
    
    Longer description explaining the purpose, behavior, and usage patterns.
    Include important details about attributes, relationships, or constraints.
    
    Attributes:
        attr1 (type): Description of attribute 1
        attr2 (type): Description of attribute 2
    """
    
    def __init__(self, param1: str, param2: int = 0):
        """Initialize the class.
        
        Args:
            param1 (str): Description of first parameter
            param2 (int): Description of second parameter (default 0)
        """
        self.attr1 = param1
        self.attr2 = param2
    
    def method(self, arg: str) -> bool:
        """Perform some action.
        
        Args:
            arg (str): Input argument description
            
        Returns:
            bool: Description of return value
            
        Raises:
            ValueError: When validation fails
        """
        # Implementation
        pass
```

### Type Hints

Use type hints for all parameters and return types:

```python
from typing import Dict, List, Optional, Any

async def analyze(self, data: Dict[str, Any]) -> AnalysisResult:
    """Analyze incident data.
    
    Args:
        data (Dict[str, Any]): Input data dictionary
        
    Returns:
        AnalysisResult: Analysis findings
    """
    pass
```

### Comments

Use comments to explain the "why", not the "what":

```python
# Bad: Obvious from code
count = count + 1  # Increment count

# Good: Explains business logic
# Only count errors if they're from production systems (not staging)
if entry['environment'] == 'production':
    error_count += 1
```

### Error Handling

Include error handling with proper logging:

```python
try:
    result = await self.analyze(data)
    logger.info(f"Analysis complete: {len(result.findings)} findings")
except Exception as e:
    logger.error(f"Analysis failed: {e}", exc_info=True)
    raise
```


## Testing

Run tests with pytest:
```bash
pytest tests/
```

Run tests with coverage:
```bash
pytest --cov=app tests/
```

Run specific test file:
```bash
pytest tests/test_log_agent.py -v
```

## License

MIT License


