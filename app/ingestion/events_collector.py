
from kubernetes import watch
from app.utils.k8s_client import K8sClient

def stream_raw_events(namespace=None):
    """
    Generator that streams raw Kubernetes events from the API.
    Args:
        namespace (str, optional): If provided, only stream events from this namespace.
    Yields:
        Raw K8s event objects as returned by the Kubernetes API.
    """
    v1 = K8sClient.get_core_v1()
    w = watch.Watch()
    func = v1.list_namespaced_event if namespace else v1.list_event_for_all_namespaces
    kwargs = {"namespace": namespace} if namespace else {}
    for event in w.stream(func, **kwargs):
        yield event["object"]