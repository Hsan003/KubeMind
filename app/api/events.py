"""
Events API endpoints for KubeMind
- /events-collector: Stream raw Kubernetes events (SSE)
- /events/push: Trigger event pipeline to push events to Kafka
"""
from fastapi.responses import StreamingResponse, JSONResponse
from fastapi import APIRouter, BackgroundTasks
from app.ingestion.events_collector import stream_raw_events
from app.models.event_model import KubernetesEvent
from app.services.event_pipeline import EventPipeline

router = APIRouter()

@router.get("/events-collector")
def events_collector(namespace: str = None):
    """
    Streams raw Kubernetes events as a Server-Sent Events (SSE) stream.
    This does NOT push events to Kafka, just streams for debugging/demo.
    """
    def event_generator():
        for event in stream_raw_events(namespace=namespace):

            standardized_event = KubernetesEvent(
                type=event.type,
                reason=event.reason,
                message=event.message,

                namespace=event.involved_object.namespace,
                object_kind=event.involved_object.kind,
                object_name=event.involved_object.name,

                timestamp=str(
                    event.last_timestamp
                    or event.event_time
                    or event.metadata.creation_timestamp
                )
            )

            response = (

                f"event: {event.type}\n"
                f"data: {standardized_event.model_dump_json()}\n\n"
            )   

            yield response
    return StreamingResponse(event_generator(), media_type="text/event-stream")


@router.post("/events/push")
def push_events_to_kafka(background_tasks: BackgroundTasks):
    """
    Triggers the event pipeline to collect K8s events and push them to Kafka.
    Runs in the background to avoid blocking the API request.
    """
    def run_pipeline():
        pipeline = EventPipeline()
        pipeline.run()  # By default, all namespaces

    background_tasks.add_task(run_pipeline)
    return JSONResponse({"detail": "Event pipeline started in background. Events will be pushed to Kafka."})