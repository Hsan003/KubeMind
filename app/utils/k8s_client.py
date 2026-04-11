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
        try:
            config.load_incluster_config()
        except:
            config.load_kube_config()