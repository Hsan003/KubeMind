from kubernetes import client, config

class K8sService:
    _instance = None  # singleton

    def __init__(self):
        self._init_client()

    def _init_client(self):
        try:
            config.load_incluster_config()
            print("Using in-cluster config")
        except:
            config.load_kube_config()
            print("Using kubeconfig")

        self.core_v1 = client.CoreV1Api()

    @classmethod
    def get_instance(cls):
        if cls._instance is None:
            cls._instance = K8sService()
        return cls._instance