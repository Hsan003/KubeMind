import logging
from kubernetes import client, config

class K8sClient:
    """Singleton Kubernetes client to manage API connections."""
    
    _core_v1 = None

    @classmethod
    def get_core_v1(cls):
        if cls._core_v1 is None:
            cls._load_config()
            cls._core_v1 = client.CoreV1Api()
        return cls._core_v1

    @staticmethod
    def _load_config():
        logger = logging.getLogger(__name__)
        try:
            config.load_incluster_config()
            return
        except Exception as exc_incluster:
            logger.debug("In-cluster Kubernetes config load failed", exc_info=True)
        try:
            config.load_kube_config()
            return
        except Exception as exc_kubeconfig:
            logger.error(
                "Unable to load Kubernetes configuration from in-cluster or kubeconfig",
                exc_info=True,
            )
            raise RuntimeError(
                "Could not load Kubernetes configuration from in-cluster config or kubeconfig"
            ) from exc_kubeconfig