from kubernetes import client, config
from kubernetes.client import CoreV1Api
import tempfile, os, base64

class K8sClient:
    def __init__(self, kubeconfig_path: str = None, api_url: str = None, token: str = None):
        if kubeconfig_path:
            # user provides their kubeconfig file path
            config.load_kube_config(config_file=kubeconfig_path)
        elif api_url and token:
            # user provides API URL + bearer token
            configuration = client.Configuration()
            configuration.host = api_url
            configuration.verify_ssl = False
            configuration.api_key = {"authorization": f"Bearer {token}"}
            client.Configuration.set_default(configuration)
        else:
            # fallback: use default kubeconfig (~/.kube/config)
            config.load_kube_config()

        self.core = CoreV1Api()

    def list_namespaces(self) -> list[str]:
        return [ns.metadata.name for ns in self.core.list_namespace().items]

    def list_pods(self, namespace: str) -> list:
        return self.core.list_namespaced_pod(namespace).items

    def fetch_pod_logs(self, pod_name: str, namespace: str, container: str, tail_lines: int = 500) -> str:
        try:
            return self.core.read_namespaced_pod_log(
                name=pod_name,
                namespace=namespace,
                container=container,
                tail_lines=tail_lines,
                timestamps=True,   # prepends timestamp to each line
            )
        except Exception:
            return ""