from enum import Enum

TKG_EXTENSIONS_ROOT = {
    "1.3.0": "/tanzu/tkg-extensions-v1.3.0+vmware.1",
    "1.3.1": "/tanzu/tkg-extensions-v1.3.1+vmware.1",
    "1.4.0": "/tanzu/tkg-standard-repo-v1.4.0",
}

CLUSTER_NODE_SIZES = ["small", "medium", "large", "extra-large"]

CLUSTER_PLAN = ["dev", "prod"]


class Paths(str, Enum):
    MASTER_SPEC_PATH = "config/deployment-config.yml"
    DESIRED_STATE_PATH = "desired-state/desired-state.yml"
    STATE_PATH = "deployment-state/state.yml"
    KUBECONFIG_REPO_PATH = "{root_dir}/kubeconfig-repo"

    # template files in package
    TEMPLATES_ROOT_DIR = "template"
    TKG_MGMT_SPEC_J2 = f"{TEMPLATES_ROOT_DIR}/deploy.yaml.j2"
    VSPHERE_SHARED_SERVICES_SPEC_J2 = f"{TEMPLATES_ROOT_DIR}/vsphere_shared_cluster_deploy.yaml.j2"
    VSPHERE_SHARED_SERVICES_SPEC = f"vsphere_shared_cluster_deploy.yml"
    GOVC_AVI_DEPLOY_CONFIG_J2 = f"{TEMPLATES_ROOT_DIR}/deploy_avi_govc_config.json.j2"
    GOVC_OVA_DEPLOY_CONFIG_J2 = f"{TEMPLATES_ROOT_DIR}/govc/node_template_config.json.j2"
    GOVC_AVI_SE_DEPLOY_CONFIG_J2 = f"{TEMPLATES_ROOT_DIR}/deploy_alb_se_template_govc_config.json.j2"
    SUPPORT_MATRIX_FILE = f"{TEMPLATES_ROOT_DIR}/support-matrix.yml"
    VSPHERE_WORKLOAD_SERVICES_SPEC_J2 = f"{TEMPLATES_ROOT_DIR}/vsphere_workload_cluster_deploy.yaml.j2"
    VSPHERE_WORKLOAD_SERVICES_SPEC = f"vsphere_workload_cluster_deploy.yml"

    # tmp local
    TMP_DIR = ".tmp"
    GOVC_AVI_DEPLOY_CONFIG = f"{TMP_DIR}/deploy_avi_govc_config.json"
    GOVC_OVA_DEPLOY_CONFIG = f"{TMP_DIR}/deploy_ova_govc_config.json"
    GOVC_AVI_SE_DEPLOY_CONFIG = f"{TMP_DIR}/deploy_avi_se_govc_config.json"
    TKG_MGMT_DEPLOY_CONFIG = f"{TMP_DIR}/deploy-tkg.yml"
    LOCAL_HARBOR_DATA_VALUES = "{root_dir}/harbor-data-values.yaml"
    LOCAL_GRAFANA_DATA_VALUES = "{root_dir}/grafana-data-values.yml"
    LOCAL_HARBOR_CA_CERT = "{root_dir}/harbor-ca.crt"
    LOCAL_EXTERNAL_DNS_DATA_VALUES = "{root_dir}/external-dns-data-values.yaml"
    LOCAL_TKG_BINARY_PATH = "{root_dir}/tanzu-cli-bundle/tanzu-cli-bundle-linux-amd64.tar"
    LOCAL_KUBECTL_BINARY_PATH = "{root_dir}/kubectl-cli/kubectl-linux-{version}.gz"
    REMOTE_KUBECTL_BINARY_PATH = "{root_dir}/kubectl-linux-{version}.gz"
    LOCAL_TMC_BINARY_PATH = "{root_dir}/tmc-cli/tmc"
    REMOTE_TMC_BINARY_PATH = "{root_dir}/tmc"

    ## kubeconfig
    KUBECONFIG_REPO = "kubeconfig-repo"
    REPO_KUBE_CONFIG = f"{KUBECONFIG_REPO}/.kube/config"
    REPO_KUBE_TKG_CONFIG = f"{KUBECONFIG_REPO}/.kube-tkg/config"
    REPO_TANZU_CONFIG = f"{KUBECONFIG_REPO}/.tanzu/config.yaml"
    REPO_TANZU_CONFIG_NEW = f"{KUBECONFIG_REPO}/.config/tanzu/config.yaml"

    ## pipeline resources
    ALB_OVA_PATH = "alb-controller-ova/controller-20.1.6-9132.ova"  # ova_path # todo fix ova path
    ALB_SE_OVA_PATH = "alb-se-ova/se.ova"

    # remote paths
    KUBE_CONFIG_TARGET_PATH = "kube-config.yml"
    TKG_EXTENSIONS_DIR = "{extensions_root}/extensions"

    CONFIG_ROOT_DIR = "/tmp"
    TKG_MGMT_CONFIG_PATH = f"{CONFIG_ROOT_DIR}/mgmt_cluster_config.yml"  # management
    TKG_SHARED_SERVICES_CONFIG_PATH = f"{CONFIG_ROOT_DIR}/shared_services_cluster_config.yml"  # shared services cluster
    TKG_WORKLOAD_CLUSTER_CONFIG_PATH = f"{CONFIG_ROOT_DIR}/workload_cluster_config.yml"

    ## kube_config paths
    REMOTE_KUBE_CONFIG = "/root/.kube/config"
    REMOTE_KUBE_TKG_CONFIG = "/root/.kube-tkg/config"
    REMOTE_TANZU_CONFIG = "/root/.tanzu/config.yaml"
    REMOTE_TANZU_CONFIG_NEW = "/root/.config/tanzu/config.yaml"

    # Paths are relative to TKG_EXTENSIONS_<VERSION>/extensions directory
    CONTOUR_NAMESPACE_CONFIG = "ingress/contour/namespace-role.yaml"
    VSPHERE_ALB_CONTOUR_CONFIG_EXAMPLE = "ingress/contour/vsphere/contour-data-values-lb.yaml.example"
    VSPHERE_ALB_CONTOUR_CONFIG = "ingress/contour/vsphere/contour-data-values.yaml"
    LOCAL_VSPHERE_ALB_CONTOUR_CONFIG = "scripts/template/contour-data-values.yaml"
    LOCAL_VSPHERE_WORKLOAD_PROMETHEUS_CONFIG = "scripts/template/prometheus-data-values.yaml"
    REMOTE_VSPHERE_WORKLOAD_PROMETHEUS_CONFIG = "/tmp/prometheus-data-values.yaml"
    REMOTE_VSPHERE_ALB_CONTOUR_CONFIG = "/tmp/contour-data-values.yaml"
    CONTOUR_EXTENSION_CONFIG = "ingress/contour/contour-extension.yaml"
    TMC_EXTENSION_MGR_CONFIG = "tmc-extension-manager.yaml"
    KAPP_CONTROLLER_CONFIG = "kapp-controller.yaml"
    CERT_MANAGER_CONFIG = "cert-manager/"
    PROMETHEUS_NAMESPACE_CONFIG = "monitoring/prometheus/namespace-role.yaml"
    PROMETHEUS_CONFIG_EXAMPLE = "monitoring/prometheus/prometheus-data-values.yaml.example"
    PROMETHEUS_CONFIG = "monitoring/prometheus/prometheus-data-values.yaml"
    PROMETHEUS_EXTENSION_CONFIG = "monitoring/prometheus/prometheus-extension.yaml"
    REMOTE_PROMETHEUS_DATA_VALUES = "/tmp/prometheus-data-values.yml"
    GRAFANA_CONFIG_EXAMPLE = "monitoring/grafana/grafana-data-values.yaml.example"
    GRAFANA_CONFIG = "monitoring/grafana/grafana-data-values.yaml"
    GRAFANA_NAMESPACE_CONFIG = "monitoring/grafana/namespace-role.yaml"
    GRAFANA_EXTENSION_CONFIG = "monitoring/grafana/grafana-extension.yaml"
    REMOTE_GRAFANA_DATA_VALUES = "/tmp/grafana-data-values.yaml"
    HARBOR_NAMESPACE_CONFIG = "registry/harbor/namespace-role.yaml"
    HARBOR_CONFIG_EXAMPLE = "registry/harbor/harbor-data-values.yaml.example"
    HARBOR_CONFIG = "registry/harbor/harbor-data-values.yaml"
    HARBOR_GENERATE_PASSWORDS = "registry/harbor/generate-passwords.sh"
    HARBOR_EXTENSION_CONFIG = "registry/harbor/harbor-extension.yaml"
    REMOTE_HARBOR_DATA_VALUES = "/tmp/harbor-data-values.yaml"
    EXTERNAL_DNS_NAMESPACE_CONFIG = "service-discovery/external-dns/namespace-role.yaml"
    EXTERNAL_DNS_WITH_CONTOUR_EXAMPLE = (
        "service-discovery/external-dns/external-dns-data-values-rfc2136-with-contour.yaml.example"
    )
    LOCAL_EXTERNAL_DNS_WITH_CONTOUR = "scripts/template/external-dns-data-values-rfc2136-with-contour.yaml"
    REMOTE_EXTERNAL_DNS_WITH_CONTOUR = "/tmp/external-dns-data-values.yaml"
    EXTERNAL_DNS_CONFIG = "service-discovery/external-dns/external-dns-data-values.yaml"
    EXTERNAL_DNS_EXTENSION_CONFIG = "service-discovery/external-dns/external-dns-extension.yaml"


class TKGCommands(str, Enum):
    VERSION = "tanzu version"
    MGMT_DEPLOY = "tanzu management-cluster create --file {file_path} -v 9"
    CLUSTER_DEPLOY = "tanzu cluster create --file {file_path} {verbose}"
    LIST_CLUSTERS_JSON = "tanzu cluster list --output json"
    LIST_ALL_CLUSTERS_JSON = "tanzu cluster list --include-management-cluster --output json"
    GET_ADMIN_CONTEXT = "tanzu cluster kubeconfig get {cluster} --admin"
    MGMT_UPGRADE_CLEANUP = """
    rm -rf ~/.tanzu/tkg/bom
    export TKG_BOM_CUSTOM_IMAGE_TAG="v1.3.1-patch1"
    tanzu management-cluster create
    tanzu login --server {cluster_name}
    kubectl delete deployment kapp-controller -n kapp-controller
    kubectl delete clusterrole kapp-controller-cluster-role
    kubectl delete clusterrolebinding kapp-controller-cluster-role-binding
    kubectl delete serviceaccount kapp-controller-sa -n kapp-controller
    """
    MGMT_UPGRADE = "tanzu management-cluster upgrade --yes {options}"
    CLUSTER_UPGRADE_CLEANUP = """
    tanzu login --server {mgmt_cluster_name}
    tanzu cluster list --include-management-cluster
    tanzu cluster kubeconfig get {cluster_name} --admin
    kubectl config use-context {cluster_name}-admin@{cluster_name}
    kubectl delete deployment kapp-controller -n kapp-controller
    kubectl delete clusterrole kapp-controller-cluster-role
    kubectl delete clusterrolebinding kapp-controller-cluster-role-binding
    kubectl delete serviceaccount kapp-controller-sa -n kapp-controller
    """
    CLUSTER_UPGRADE = "tanzu cluster upgrade {cluster_name} --yes {options}"
    GET_K8_RELEASES = """
    tanzu kubernetes-release get
    tanzu kubernetes-release available-upgrades get {tkr}
    """
    UPDATE_TKG_BOM = """
    rm -rf ~/.tanzu/tkg/bom
    export TKG_BOM_CUSTOM_IMAGE_TAG="{bom_image_tag}"
    tanzu management-cluster create
    """
    TANZU_LOGIN = "tanzu login --server {server}"
    MGMT_CLUSTER_UPGRADE = "tanzu management-cluster upgrade --yes {options}"
    TIMEOUT_OPTION = " --timeout {timeout} "

    LIST_ALL_CLUSTERS = "tanzu cluster list --include-management-cluster"
    LIST_AVAILABLE_PACKAGES = "tanzu package available list -A {options}"
    GET_AVAILABLE_PACKAGE_DETAILS = "tanzu package available list {pkgName} -A {options}"
    INSTALL_PACKAGE = "tanzu package install {name} --package-name {pkgName} --namespace {namespace} --version {version} {options}"
    LIST_INSTALLED_PACKAGES = "tanzu package installed list -A {options}"
    GET_PACKAGE_DETAILS = "tanzu package installed get {name} --namespace {namespace} {options}"
    REGISTER_TMC = "tanzu management-cluster register --'tmc'-registration-url \"{url}\""


class TanzuToolsCommands(dict, Enum):
    KUBECTL = {"version": "kubectl version --client --short", "prefix": "Client Version: ", "matrix-key": "kubectl"}
    YTT = {"version": "ytt version", "prefix": "ytt version ", "matrix-key": "ytt"}
    KAPP = {"version": "kapp version", "prefix": "kapp version ", "matrix-key": "kapp"}
    KBLD = {"version": "kbld version", "prefix": "kbld version ", "matrix-key": "kbld"}
    IMGPKG = {"version": "imgpkg version", "prefix": "imgpkg version ", "matrix-key": "imgpkg"}
    YQ = {"version": "yq --version", "prefix": "yq version ", "matrix-key": "yq"}
    JQ = {"version": "jq --version", "prefix": "jq-", "matrix-key": "jq"}


class PrepareEnvCommands(str, Enum):
    DOCKER_RUN_CMD = """
    docker rm -f arcas-tkg
    docker run -d --restart=always -it --privileged --net=host --name=arcas-tkg \
        -v /var/run/docker.sock:/var/run/docker.sock \
        -v /usr/bin/docker:/usr/bin/docker \
        {image_name}:{tkg_version}
    """
    VALIDATE_DOCKER_RUNNING = "docker container ls --filter 'name=arcas-tkg' -f 'status=running'"
    CLEANUP_KIND_CONTAINERS = """
    docker ps -a
    echo "Kind container ID's:"
    docker container ls -a -q --filter 'name=tkg-kind-*'
    echo "Removing kind clusters..."
    docker rm -f $(docker container ls -a -q --filter 'name=tkg-kind-*')
    docker ps -a
    """
    ROOT_DIR = "/tanzu"
    UNTAR_TKG_CLI = """
    cd /tanzu && \
    tar -xvf tanzu-cli-bundle-linux-amd64.tar && \
    """
    COPY_EXT = """
    cd /tanzu && \
    cp {version}/tkg-extensions* /tanzu/
    """
    COPY_PKG = """
    cd /root/tanzu && \
    cp {version}/tkg-standard-repo* /root/tanzu/
    """
    CLEANUP_ALL = """
    rm -rf ~/.config/tanzu/config.yaml && \
    rm -rf ~/.kube/ && \
    rm -rf ~/.kube-tkg/ && \
    rm -rf ~/.tanzu/  && \
    rm -rf ~/.config/  && \
    rm -rf ~/.local/share/tanzu-cli/
    rm -rf /tanzu/*
    ls /tanzu || mkdir -p /tanzu
    """
    INSTALL_TANZU = """
    cd /tanzu && \
    ls tanzu-cli-bundle-linux-amd64.tar && \
    tar -xvf tanzu-cli-bundle-linux-amd64.tar && \
    install cli/core/v{version}/tanzu-core-linux_amd64 /usr/local/bin/tanzu
    """
    INSTALL_KUBECTL = """
    cd /tanzu && \
    ls kubectl-linux-{version}.gz && \
    gunzip kubectl-linux-{version}.gz && \
    install kubectl-linux-{version}  /usr/local/bin/kubectl
    """
    INSTALL_YQ = """
    cd /tanzu && \
    (wget https://github.com/mikefarah/yq/releases/download/{version}/yq_linux_amd64 || \
    wget https://github.com/mikefarah/yq/releases/download/v{version}/yq_linux_amd64) && \
    mv yq_linux_amd64 /usr/local/bin/yq && \
    chmod +x /usr/local/bin/yq
    """
    INSTALL_JQ = """
    cd /tanzu && \
    wget -O jq https://github.com/stedolan/jq/releases/download/jq-{version}/jq-linux64 && \
    chmod +x jq && \
    mv jq /usr/local/bin/jq
    """
    INSTALL_PLUGIN = """
    cd /tanzu && \
    tanzu plugin clean && \
    tanzu plugin install --local cli all && \
    tanzu plugin list
    """
    INSTALL_YTT = """
    cd /tanzu && \
    gunzip cli/ytt-linux-amd64-v{version}+vmware.1.gz && \
    chmod ugo+x cli/ytt-linux-amd64-v{version}+vmware.1 && \
    mv cli/ytt-linux-amd64-v{version}+vmware.1 /usr/local/bin/ytt
    """
    INSTALL_KAPP = """
    cd /tanzu && \
    gunzip cli/kapp-linux-amd64-v{version}+vmware.1.gz && \
    chmod ugo+x cli/kapp-linux-amd64-v{version}+vmware.1 && \
    mv cli/kapp-linux-amd64-v{version}+vmware.1 /usr/local/bin/kapp
    """
    INSTALL_KBLD = """
    cd /tanzu && \
    gunzip cli/kbld-linux-amd64-v{version}+vmware.1.gz && \
    chmod ugo+x cli/kbld-linux-amd64-v{version}+vmware.1 && \
    mv cli/kbld-linux-amd64-v{version}+vmware.1 /usr/local/bin/kbld
    """
    INSTALL_IMGPKG = """
    cd /tanzu && \
    gunzip cli/imgpkg-linux-amd64-v{version}+vmware.1.gz && \
    chmod ugo+x cli/imgpkg-linux-amd64-v{version}+vmware.1 && \
    mv cli/imgpkg-linux-amd64-v{version}+vmware.1 /usr/local/bin/imgpkg
    """
    INSTALL_EXT = """
    cd /tanzu && \
    ls tkg-extensions-manifests-v{version}+vmware.1.tar.gz && \
    tar -xzf tkg-extensions-manifests-v{version}+vmware.1.tar.gz
    """
    INSTALL_PKG = """
    cd /root/tanzu && \
    ls tkg-standard-repo-v{version}.tar.gz && \
    tar -xzf tkg-standard-repo-v{version}.tar.gz
    """
    CLEANUP_TANZU_DIR = """
    cd /tanzu && \
    rm -f tanzu-cli-bundle-linux-amd64.tar && \
    rm -rf cli && \
    rm -f kubectl-linux-v*+vmware.1* && \
    rm -f tkg-extensions-manifests-v*+vmware.1.tar.gz
    """

    INSTALL_TMC = """
    cd /tanzu && \
    chmod +x tmc && mv tmc /usr/local/bin/
    """

class KubectlCommands(str, Enum):
    VERSION = "kubectl version --client --short"
    SET_KUBECTL_CONTEXT = "kubectl config use-context {cluster}-admin@{cluster}"
    ADD_SERVICES_LABEL = 'kubectl label cluster.cluster.x-k8s.io/{cluster} cluster-role.tkg.tanzu.vmware.com/tanzu-services="" --overwrite=true'
    GET_ALL_PODS = "kubectl get pods -A"
    APPLY = "kubectl apply -f {config_file}"
    LIST_NAMESPACES = "kubectl get namespaces {options}"
    LIST_APPS = "kubectl get apps -n {namespace} {options}"
    GET_APP_DETAILS = "kubectl get app {app_name} -n {namespace} {options}"
    LIST_SECRETS = "kubectl get secret -n {namespace} {options}"
    FILTER_NAME = "-o=name"
    FILTER_JSONPATH = "-o=jsonpath={template}"
    OUTPUT_YAML = "-o yaml"
    OUTPUT_JSON = "-o json"
    CREATE_SECRET = "kubectl create secret generic {name} --from-file={config_file} -n {namespace}"
    LIST_SERVICE_ACCOUNTS = "kubectl get serviceaccounts -n {namespace} {options}"
    GET_HARBOR_CERT = "kubectl -n {namespace} get secret harbor-tls {options}"
    DELETE = "kubectl delete -f {config_file}"
    DELETE_EXTENSION = "kubectl delete extension {app_name} -n {namespace}"
    GET_SECRET_DETAILS = "kubectl get secret {name} -n {namespace} {options}"
    UPDATE_SECRET = "kubectl create secret generic {name} --from-file={config_file} -n {namespace} -o yaml --dry-run | kubectl replace -f-"

class TmcCommands(str, Enum):
    LOGIN = "export TMC_API_TOKEN={token} && tmc login --no-configure --name arcas"
    GET_KUBECONFIG = "tanzu cluster kubeconfig get {cluster_name} --admin --export-file {file}"
    ATTACH_CLUSTER = "tmc cluster attach --name  {cluster_name} --cluster-group {cluster_group} -k kubeconfig_cluster.yaml --force"

class Constants(str, Enum):
    MANAGEMENT_ROLE = "management"
    TANZU_SERVICES_ROLE = "tanzu-services"
    TANZU_SYSTEM_INGRESS = "tanzu-system-ingress"
    TANZU_SYSTEM_MONITORING = "tanzu-system-monitoring"
    TANZU_SYSTEM_REGISTRY = "tanzu-system-registry"
    TANZU_SYSTEM_SERVICE_DISCOVERY = "tanzu-system-service-discovery"
    VMWARE_SYSTEM_TMC = "vmware-system-tmc"
    CONTOUR_APP = "contour"
    CONTOUR_DATA_VALUES = "contour-data-values"
    CONTOUR_SERVICE_ACCOUNT = "contour-extension-sa"
    PROMETHEUS_DATA_VALUES = "prometheus-data-values"
    PROMETHEUS_APP = "prometheus"
    PROMETHEUS_SERVICE_ACCOUNT = "prometheus-extension-sa"
    PROMETHEUS_PACKAGE = "prometheus.tanzu.vmware.com"
    GRAFANA_APP = "grafana"
    GRAFANA_DATA_VALUES = "grafana-data-values"
    GRAFANA_SERVICE_ACCOUNT = "grafana-extension-sa"
    GRAFANA_ADMIN_PASSWORD_TOKEN = r"admin_password: .*"
    GRAFANA_ADMIN_PASSWORD_VALUE = "admin_password: {password}"
    GRAFANA_DATA_VALUES_NAMESPACE = r"namespace: .*"
    GRAFANA_DATA_VALUES_NEW_NAMESPACE = "namespace: {namespace}"
    GRAFANA_PACKAGE = "grafana.tanzu.vmware.com"
    GRAFANA_NAMESPACE = "tanzu-system-dashboards"
    HARBOR_SERVICE_ACCOUNT = "harbor-extension-sa"
    HARBOR_DATA_VALUES = "harbor-data-values"
    HARBOR_APP = "harbor"
    HARBOR_ADMIN_PASSWORD_TOKEN = r"harborAdminPassword: .*"
    HARBOR_ADMIN_PASSWORD_SUB = "harborAdminPassword: {password}"
    HARBOR_HOSTNAME_TOKEN = r"hostname: .*"
    HARBOR_HOSTNAME_SUB = "hostname: {hostname}"
    # Time in seconds
    RECONCILE_WAIT_TIMEOUT = 900
    RECONCILE_WAIT_INTERVAL = 20
    RECONCILE_SUCCESS = "Reconcile succeeded"
    RECONCILE_FAILED = "Reconcile failed"
    EXTERNAL_DNS_SERVICE_ACCOUNT = "external-dns-extension-sa"
    EXTERNAL_DNS_DATA_VALUES = "external-dns-data-values"
    EXTERNAL_DNS_APP = "external-dns"
    RFC2136_DNS_SERVER_TOKEN = r"--rfc2136-host=[\d\.]*"
    RFC2136_DNS_SERVER_SUB = "--rfc2136-host={server}"
    RFC2136_DNS_DOMAIN_TOKEN = "my-zone.example.org"
    RFC2136_DNS_DOMAIN_SUB = "{domain}"
    RFC2136_DNS_TSIG_KEY_TOKEN = "externaldns-key"
    RFC2136_DNS_TSIG_KEY_SUB = "{tsig_key}"
    RFC2136_DNS_TSIG_SECRET_TOKEN = "REPLACE_ME_WITH_TSIG_SECRET"
    RFC2136_DNS_TSIG_SECRET_SUB = "{tsig_secret}"
    CERT_MGR_PACKAGE = "cert-manager.tanzu.vmware.com"
    CERT_MGR_DISPLAY_NAME = "cert-manager"
    CERT_MGR_APP = "cert-manager"
    CONTOUR_PACKAGE = "contour.tanzu.vmware.com"
    CONTOUR_DISPLAY_NAME = "Contour"
    EXTERNAL_DNS_PACKAGE = "external-dns.tanzu.vmware.com"
    EXTERNAL_DNS_DISPLAY_NAME = "external-dns"
    HARBOR_PACKAGE = "harbor.tanzu.vmware.com"
    HARBOR_DISPLAY_NAME = "Harbor"


class RepaveTkgCommands(str, Enum):
    """kubectl get nodes -A --sort-by=.metadata.creationTimestamp -o jsonpath='{.items[:1].metadata.name}'"""

    GET_OLDEST_WORKER_NODE = """
    kubectl get nodes -A --sort-by=.metadata.creationTimestamp \
        -o jsonpath='{range .items[*]}{.metadata.name}{"\\n"}{end}' | grep "md" | head -1
    """
    GET_NODES_WITH_TIMESTAMP = """
    kubectl get nodes -A --sort-by=.metadata.creationTimestamp \
        -o jsonpath='{range .items[*]}{.metadata.creationTimestamp}  {.metadata.name}{"\\n"}{end}'
    """
    ADD_NODES = """
    tanzu cluster scale {cluster_name} \
        --controlplane-machine-count {control_plane_node_count} \
        --worker-machine-count {worker_node_count}
    """
    NODE_COUNT = """
    kubectl get nodes -A -o json | jq -c -r '.items | length' 
    """
    NODE_STATUS = """
    kubectl get nodes -A  -o jsonpath='[{range .items[*]}{.status.conditions[?(@.type=="Ready")]}{",\\n"}{end}]'
    """
    DRAIN_PODS = "kubectl drain {node_name}  --delete-emptydir-data --ignore-daemonsets"
    DELETE_NODE = "kubectl delete node {node_name}"


class Task(str, Enum):
    DEPLOY_CLUSTER = "DEPLOY_CLUSTER"
    DEPLOY_CONTOUR = "DEPLOY_CONTOUR"
    DEPLOY_EXTERNAL_DNS = "DEPLOY_EXTERNAL_DNS"
    DEPLOY_HARBOR = "DEPLOY_HARBOR"
    DEPLOY_CERT_MANAGER = "DEPLOY_CERT_MANAGER"
    DEPLOY_PROMETHEUS = "DEPLOY_PROMETHEUS"
    DEPLOY_GRAFANA = "DEPLOY_GRAFANA"
    ATTACH_CLUSTER_TO_TMC = "ATTACH_CLUSTER_TO_TMC"
    UPGRADE_CLUSTER = "UPGRADE_CLUSTER"
    UPGRADE_CONTOUR = "UPGRADE_CONTOUR"
    UPGRADE_EXTERNAL_DNS = "UPGRADE_EXTERNAL_DNS"
    UPGRADE_HARBOR = "UPGRADE_HARBOR"
    UPGRADE_CERT_MANAGER = "UPGRADE_CERT_MANAGER",
    UPGRADE_PROMETHEUS = "UPGRADE_PROMETHEUS"
    UPGRADE_GRAFANA = "UPGRADE_GRAFANA"


class ComponentPrefix(str, Enum):
    ALB_MGMT_NW = "tkg-avi-mgmt"
    MGMT_CLU_NW = "tkg-management"
    SHARED_CLU_NW = "tkg-shared-service"
    MGMT_DATA_VIP_NW = "tkg-mgmt-data"
    CLUSTER_VIP_NW = "tkg-cluster-vip"
    WORKLOAD_CLU_NW = "tkg-workload"
    WORKLOAD_DATA_VIP_NW = "tkg-workload-data"
    DNS_IPS = "tkg-infra-dns-ips"
    NTP_IPS = "tkg-infra-ntp-ips"
    VC_IP = "tkg-infra-vcenter-ip"
    KUBE_VIP_SERVICE = "tkg-kube-api"
    KUBE_VIP_SERVICE_ENTRY = "tkg-kube-api-service-entry"
    ESXI = "ESXI"


class FirewallRulePrefix(str, Enum):
    INFRA_TO_NTP = "tkg-alb-to-ntp"
    INFRA_TO_DNS = "tkg-alb-to-dns"
    INFRA_TO_VC = "tkg-alb-to-vcenter"
    INFRA_TO_ANY = "tkg-to-external"
    INFRA_TO_ALB = "tkg-to-alb"
    INFRA_TO_CLUSTER_VIP = "tkg-to-cluster-vip"
    MGMT_TO_ESXI = "tkg-mgmt-to-esxi"
    WORKLOAD_TO_VC = "tkg-workload{index}-to-vc"


class VmcNsxtGateways(str, Enum):
    CGW = "cgw"
    MGW = "mgw"


class NsxtServicePaths(str, Enum):
    HTTPS = "/infra/services/HTTPS"
    NTP = "/infra/services/NTP"
    DNS = "/infra/services/DNS"
    DNS_UDP = "/infra/services/DNS-UDP"
    ANY = "ANY"


class NsxtScopes(str, Enum):
    CGW_ALL = "/infra/labels/cgw-all"
    MGW = "/infra/labels/mgw"


class AlbPrefix(str, Enum):
    CLOUD_NAME = "tkg-cloud"
    MGMT_SE_GROUP = "tkg-management-se-group"
    WORKLOAD_SE_GROUP = "tkg-workload-se-group"
    MGMT_SE_NODE = "tkg-management-se"
    WORKLOAD_SE_NODE = "tkg-workload-se"


class AlbCloudType(str, Enum):
    NONE = "none"
    VSPHERE = "vsphere"
    NSX_T_CLOUD = "nsx_t_cloud"


class VmPowerState(str, Enum):
    ON = "on"
    OFF = "off"


class AlbLicenseTier(str, Enum):
    ENTERPRISE = "ENTERPRISE"
    ESSENTIALS = "ESSENTIALS"


class AlbVrfContext(str, Enum):
    GLOBAL = "global"
    MANAGEMENT = "management"


class AkoType:
    KEY = "type"
    VALUE = "management"