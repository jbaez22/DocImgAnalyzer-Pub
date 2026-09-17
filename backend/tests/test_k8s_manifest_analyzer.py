import pytest

from app.models.schemas import Severity
from app.services import k8s_manifest_analyzer

GOOD_MANIFEST = """\
apiVersion: apps/v1
kind: Deployment
metadata:
  name: web-app
  namespace: default
spec:
  replicas: 2
  selector:
    matchLabels:
      app: web-app
  template:
    metadata:
      labels:
        app: web-app
    spec:
      hostNetwork: false
      hostPID: false
      automountServiceAccountToken: false
      securityContext:
        runAsNonRoot: true
        runAsUser: 1000
        seccompProfile:
          type: RuntimeDefault
      containers:
        - name: web
          image: nginx:1.29-alpine
          securityContext:
            privileged: false
            allowPrivilegeEscalation: false
            readOnlyRootFilesystem: true
            capabilities:
              drop: ["ALL"]
          resources:
            requests:
              cpu: 100m
              memory: 128Mi
            limits:
              cpu: 250m
              memory: 256Mi
          livenessProbe:
            httpGet:
              path: /healthz
              port: 8080
          readinessProbe:
            httpGet:
              path: /ready
              port: 8080
      volumes: []
"""

BAD_MANIFEST = """\
apiVersion: apps/v1
kind: Deployment
metadata:
  name: web-app
  namespace: default
spec:
  replicas: 2
  selector:
    matchLabels:
      app: web-app
  template:
    metadata:
      labels:
        app: web-app
    spec:
      hostNetwork: true
      hostPID: true
      containers:
        - name: web
          image: nginx
          securityContext:
            privileged: true
            allowPrivilegeEscalation: true
            capabilities:
              add: ["SYS_ADMIN"]
            readOnlyRootFilesystem: false
          env:
            - name: DATABASE_PASSWORD
              value: "supersecret123"
          volumeMounts:
            - name: host-data
              mountPath: /data
      volumes:
        - name: host-data
          hostPath:
            path: /var/lib/docker
"""


def test_good_manifest_high_score():
    result = k8s_manifest_analyzer.analyze(GOOD_MANIFEST)
    assert result.score == 100


def test_good_manifest_no_findings():
    result = k8s_manifest_analyzer.analyze(GOOD_MANIFEST)
    assert result.findings == []


def test_bad_manifest_score_zero():
    result = k8s_manifest_analyzer.analyze(BAD_MANIFEST)
    assert result.score == 0


def test_bad_manifest_all_rules_fire_exactly_once():
    result = k8s_manifest_analyzer.analyze(BAD_MANIFEST)
    rule_ids = [f.rule_id for f in result.findings]
    expected = [f"K{n:03d}" for n in range(1, 14)]
    assert sorted(rule_ids) == sorted(expected)


def test_unpinned_image_detected():
    result = k8s_manifest_analyzer.analyze(BAD_MANIFEST)
    finding = next(f for f in result.findings if f.rule_id == "K001")
    assert finding.severity == Severity.error


def test_privileged_container_detected():
    result = k8s_manifest_analyzer.analyze(BAD_MANIFEST)
    finding = next(f for f in result.findings if f.rule_id == "K002")
    assert finding.severity == Severity.error


def test_no_run_as_non_root_detected():
    result = k8s_manifest_analyzer.analyze(BAD_MANIFEST)
    finding = next(f for f in result.findings if f.rule_id == "K003")
    assert finding.severity == Severity.error


def test_allow_privilege_escalation_detected():
    result = k8s_manifest_analyzer.analyze(BAD_MANIFEST)
    finding = next(f for f in result.findings if f.rule_id == "K004")
    assert finding.severity == Severity.warning


def test_missing_resources_detected():
    result = k8s_manifest_analyzer.analyze(BAD_MANIFEST)
    finding = next(f for f in result.findings if f.rule_id == "K005")
    assert finding.severity == Severity.warning


def test_host_namespace_sharing_detected_once():
    result = k8s_manifest_analyzer.analyze(BAD_MANIFEST)
    findings = [f for f in result.findings if f.rule_id == "K006"]
    assert len(findings) == 1
    assert "hostNetwork" in findings[0].description
    assert "hostPID" in findings[0].description


def test_host_path_volume_detected():
    result = k8s_manifest_analyzer.analyze(BAD_MANIFEST)
    finding = next(f for f in result.findings if f.rule_id == "K007")
    assert "/var/lib/docker" in finding.description


def test_capabilities_not_minimized_detected():
    result = k8s_manifest_analyzer.analyze(BAD_MANIFEST)
    finding = next(f for f in result.findings if f.rule_id == "K008")
    assert "SYS_ADMIN" in finding.description


def test_no_health_probes_detected():
    result = k8s_manifest_analyzer.analyze(BAD_MANIFEST)
    finding = next(f for f in result.findings if f.rule_id == "K009")
    assert finding.severity == Severity.info


def test_writable_root_filesystem_detected():
    result = k8s_manifest_analyzer.analyze(BAD_MANIFEST)
    finding = next(f for f in result.findings if f.rule_id == "K010")
    assert finding.severity == Severity.info


def test_hardcoded_secret_env_value_detected():
    result = k8s_manifest_analyzer.analyze(BAD_MANIFEST)
    finding = next(f for f in result.findings if f.rule_id == "K011")
    assert finding.severity == Severity.error
    assert "DATABASE_PASSWORD" in finding.description


def test_secret_key_ref_not_flagged():
    manifest = """\
apiVersion: v1
kind: Pod
metadata:
  name: uses-secret-ref
spec:
  containers:
    - name: app
      image: nginx:1.29-alpine
      env:
        - name: DATABASE_PASSWORD
          valueFrom:
            secretKeyRef:
              name: db-credentials
              key: password
"""
    result = k8s_manifest_analyzer.analyze(manifest)
    assert not any(f.rule_id == "K011" for f in result.findings)


def test_non_secret_env_value_not_flagged():
    manifest = """\
apiVersion: v1
kind: Pod
metadata:
  name: normal-env
spec:
  containers:
    - name: app
      image: nginx:1.29-alpine
      env:
        - name: LOG_LEVEL
          value: "debug"
"""
    result = k8s_manifest_analyzer.analyze(manifest)
    assert not any(f.rule_id == "K011" for f in result.findings)


def test_automount_service_account_token_detected():
    result = k8s_manifest_analyzer.analyze(BAD_MANIFEST)
    finding = next(f for f in result.findings if f.rule_id == "K012")
    assert finding.severity == Severity.warning


def test_automount_service_account_token_disabled_not_flagged():
    result = k8s_manifest_analyzer.analyze(GOOD_MANIFEST)
    assert not any(f.rule_id == "K012" for f in result.findings)


def test_missing_seccomp_profile_detected():
    result = k8s_manifest_analyzer.analyze(BAD_MANIFEST)
    finding = next(f for f in result.findings if f.rule_id == "K013")
    assert finding.severity == Severity.warning


def test_runtime_default_seccomp_profile_not_flagged():
    result = k8s_manifest_analyzer.analyze(GOOD_MANIFEST)
    assert not any(f.rule_id == "K013" for f in result.findings)


def test_host_namespace_sharing_is_error_for_non_daemonset():
    result = k8s_manifest_analyzer.analyze(BAD_MANIFEST)
    finding = next(f for f in result.findings if f.rule_id == "K006")
    assert finding.severity == Severity.error


def test_host_namespace_sharing_is_downgraded_to_warning_for_daemonset():
    manifest = """\
apiVersion: apps/v1
kind: DaemonSet
metadata:
  name: node-exporter
spec:
  selector:
    matchLabels:
      app: node-exporter
  template:
    metadata:
      labels:
        app: node-exporter
    spec:
      hostNetwork: true
      hostPID: true
      containers:
        - name: node-exporter
          image: prom/node-exporter:v1.8.2
"""
    result = k8s_manifest_analyzer.analyze(manifest)
    finding = next(f for f in result.findings if f.rule_id == "K006")
    assert finding.severity == Severity.warning


def test_host_path_volume_is_warning_for_non_daemonset():
    result = k8s_manifest_analyzer.analyze(BAD_MANIFEST)
    finding = next(f for f in result.findings if f.rule_id == "K007")
    assert finding.severity == Severity.warning


def test_host_path_volume_is_downgraded_to_info_for_daemonset():
    manifest = """\
apiVersion: apps/v1
kind: DaemonSet
metadata:
  name: log-collector
spec:
  selector:
    matchLabels:
      app: log-collector
  template:
    metadata:
      labels:
        app: log-collector
    spec:
      containers:
        - name: collector
          image: fluent-bit:3.1.9
          volumeMounts:
            - name: varlog
              mountPath: /var/log
      volumes:
        - name: varlog
          hostPath:
            path: /var/log
"""
    result = k8s_manifest_analyzer.analyze(manifest)
    finding = next(f for f in result.findings if f.rule_id == "K007")
    assert finding.severity == Severity.info


def test_no_health_probes_skipped_for_job():
    manifest = """\
apiVersion: batch/v1
kind: Job
metadata:
  name: db-migration
spec:
  template:
    spec:
      restartPolicy: Never
      containers:
        - name: migrate
          image: migrate/migrate:v4.18.1
"""
    result = k8s_manifest_analyzer.analyze(manifest)
    assert not any(f.rule_id == "K009" for f in result.findings)


def test_no_health_probes_skipped_for_cronjob():
    manifest = """\
apiVersion: batch/v1
kind: CronJob
metadata:
  name: nightly-backup
spec:
  schedule: "0 2 * * *"
  jobTemplate:
    spec:
      template:
        spec:
          restartPolicy: OnFailure
          containers:
            - name: backup
              image: backup-tool:2.3.0
"""
    result = k8s_manifest_analyzer.analyze(manifest)
    assert not any(f.rule_id == "K009" for f in result.findings)


def test_no_health_probes_still_fires_for_deployment():
    result = k8s_manifest_analyzer.analyze(BAD_MANIFEST)
    assert any(f.rule_id == "K009" for f in result.findings)


def test_init_container_not_flagged_for_missing_probes():
    manifest = """\
apiVersion: v1
kind: Pod
metadata:
  name: with-init
spec:
  initContainers:
    - name: init
      image: busybox:1.36
      securityContext:
        runAsNonRoot: true
        allowPrivilegeEscalation: false
        readOnlyRootFilesystem: true
        capabilities:
          drop: ["ALL"]
      resources:
        requests:
          cpu: 10m
          memory: 16Mi
        limits:
          cpu: 50m
          memory: 32Mi
  containers:
    - name: web
      image: nginx:1.29-alpine
      securityContext:
        runAsNonRoot: true
        allowPrivilegeEscalation: false
        readOnlyRootFilesystem: true
        capabilities:
          drop: ["ALL"]
      resources:
        requests:
          cpu: 100m
          memory: 128Mi
        limits:
          cpu: 250m
          memory: 256Mi
      livenessProbe:
        httpGet:
          path: /healthz
          port: 8080
      readinessProbe:
        httpGet:
          path: /ready
          port: 8080
"""
    result = k8s_manifest_analyzer.analyze(manifest)
    assert not any(f.rule_id == "K009" for f in result.findings)


def test_digest_pinned_image_not_flagged():
    manifest = """\
apiVersion: v1
kind: Pod
metadata:
  name: digest-pinned
spec:
  containers:
    - name: web
      image: nginx@sha256:aaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaa
"""
    result = k8s_manifest_analyzer.analyze(manifest)
    assert not any(f.rule_id == "K001" for f in result.findings)


def test_cronjob_pod_spec_extracted():
    manifest = """\
apiVersion: batch/v1
kind: CronJob
metadata:
  name: nightly-job
spec:
  schedule: "0 0 * * *"
  jobTemplate:
    spec:
      template:
        spec:
          containers:
            - name: worker
              image: busybox
"""
    result = k8s_manifest_analyzer.analyze(manifest)
    assert result.metadata["container_count"] == 1
    assert any(f.rule_id == "K001" for f in result.findings)


def test_non_dict_document_skipped():
    manifest = "- just\n- a\n- list\n"
    with pytest.raises(ValueError):
        k8s_manifest_analyzer.analyze(manifest)


def test_malformed_yaml_raises_value_error():
    with pytest.raises(ValueError):
        k8s_manifest_analyzer.analyze("not: valid: yaml: [")


def test_no_supported_workload_raises_value_error():
    with pytest.raises(ValueError):
        k8s_manifest_analyzer.analyze(
            "apiVersion: v1\nkind: ConfigMap\nmetadata:\n  name: cfg\ndata:\n  key: value\n"
        )


def test_empty_content_raises_value_error():
    with pytest.raises(ValueError):
        k8s_manifest_analyzer.analyze("")
