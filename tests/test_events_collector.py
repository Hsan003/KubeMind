# test event collector 
# app and the test are not in the same directory, so we need to adjust the import path
import sys
import os
sys.path.append(os.path.abspath(os.path.join(os.path.dirname(__file__), '..')))
from app.services.event_pipeline import EventPipeline

def test_stream_events():
    """Test the event streaming from Kubernetes API."""
    pipeline = EventPipeline()
    
    # We will run the pipeline for a short duration to test the streaming
    import threading
    import time

    pipeline.run(namespace="demo")  # Test with default namespace


    

#main function to run the test
if __name__ == "__main__":
    test_stream_events()