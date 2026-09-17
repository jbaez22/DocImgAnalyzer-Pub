import re
from dataclasses import dataclass, field
from typing import Any

import yaml

from app.models.schemas import Finding, Severity

_WORKLOAD_KINDS = frozenset(
    ["Pod", "Deployment", "StatefulSet", "DaemonSet", "Job", "ReplicaSet", "CronJob"]
)
_HOST_NAMESPACE_FLAGS = ("hostNetwork", "hostPID", "hostIPC")

# Run-to-completion workloads don't have a steady request-serving state for a
# liveness/readiness probe to check — K009 doesn't apply to them.
_PROBE_EXEMPT_KINDS = frozenset(["Job", "CronJob"])

# Env/arg key names that suggest a secret value — same pattern as
# dockerfile_analyzer.py's R004. No \b boundaries — underscore is \w so \b
# fails on DB_PASSWORD, API_TOKEN, etc. Substring match is intentional.
_SECRET_PATTERN = re.compile(
    r"(password|passwd|pwd|secret|token|api_key|apikey|credential|private_key|access_key)",
    re.IGNORECASE,
)

_SAFE_SECCOMP_TYPES = frozenset(["RuntimeDefault", "Localhost"])


@dataclass
class AnalysisResult:
    score: int = 100
    findings: list[Finding] = field(default_factory=list)
    metadata: dict[str, Any] = field(default_factory=dict)


@dataclass
class _Workload:
    kind: str
    name: str
    pod_spec: dict[str, Any]


def _pod_spec_for(kind: str, doc: dict[str, Any]) -> dict[str, Any]:
    """Locate the PodSpec inside a workload manifest, by kind."""
    spec = doc.get("spec") or {}
    if kind == "Pod":
        return spec
    if kind == "CronJob":
        job_template = spec.get("jobTemplate") or {}
        spec = job_template.get("spec") or {}
    template = spec.get("template") or {}
    return template.get("spec") or {}


def _extract_workloads(documents: list[Any]) -> list[_Workload]:
    workloads: list[_Workload] = []
    for doc in documents:
        if not isinstance(doc, dict):
            continue
        kind = doc.get("kind")
        if kind not in _WORKLOAD_KINDS:
            continue
        name = (doc.get("metadata") or {}).get("name", "<unnamed>")
        workloads.append(
            _Workload(kind=kind, name=name, pod_spec=_pod_spec_for(kind, doc))
        )
    return workloads


def _containers(pod_spec: dict[str, Any]) -> list[tuple[dict[str, Any], bool]]:
    """Return (container, is_init_container) pairs for a PodSpec."""
    regular = [(c, False) for c in (pod_spec.get("containers") or [])]
    init = [(c, True) for c in (pod_spec.get("initContainers") or [])]
    return regular + init


def _security_context(obj: dict[str, Any]) -> dict[str, Any]:
    return obj.get("securityContext") or {}


def _is_unpinned_image(image: str) -> bool:
    """Return True if the image has no tag, uses ':latest', and isn't digest-pinned."""
    if "@sha256:" in image:
        return False
    last_segment = image.split("/")[-1]
    if ":" not in last_segment:
        return True
    return last_segment.split(":")[-1] == "latest"


def _unpinned_fix(image: str) -> str:
    last_segment = image.split("/")[-1]
    prefix = image[: -len(last_segment)] if "/" in image else ""
    base = last_segment.split(":")[0].split("@")[0]
    return f"image: {prefix}{base}:<specific-version>"


def analyze(content: str) -> AnalysisResult:
    result = AnalysisResult()
    deductions = 0

    try:
        documents = [doc for doc in yaml.safe_load_all(content) if doc]
    except yaml.YAMLError as exc:
        raise ValueError(f"Invalid YAML: {exc}") from exc

    if not documents:
        raise ValueError("No YAML documents found in manifest")

    workloads = _extract_workloads(documents)
    if not workloads:
        raise ValueError(
            "No supported Kubernetes workload found (expected one of: "
            "Pod, Deployment, StatefulSet, DaemonSet, Job, ReplicaSet, CronJob)"
        )

    container_count = 0

    for workload in workloads:
        pod_spec = workload.pod_spec
        pod_security_context = _security_context(pod_spec)

        # ── K006: hostNetwork / hostPID / hostIPC ────────────────────────────────
        # DaemonSets are the one kind where hostNetwork/hostPID are a mainstream,
        # widely-used pattern (kube-proxy, CNI plugins, node-exporter-style metrics
        # agents all need host network/process visibility) — downgraded one tier for
        # DaemonSet specifically, same treatment as K007 below. `privileged` (K002)
        # is deliberately NOT given the same treatment: it's a narrower, higher-risk
        # elevation even among DaemonSets (most don't need it), so it stays at full
        # severity for every kind.
        is_daemonset = workload.kind == "DaemonSet"
        host_flags = [
            flag for flag in _HOST_NAMESPACE_FLAGS if pod_spec.get(flag) is True
        ]
        if host_flags:
            note = (
                " Commonly required for node-level DaemonSets (kube-proxy, CNI "
                "plugins, metrics agents) — verify this one actually needs it."
                if is_daemonset
                else ""
            )
            result.findings.append(
                Finding(
                    rule_id="K006",
                    severity=Severity.warning if is_daemonset else Severity.error,
                    title="Host namespace sharing enabled",
                    description=(
                        f"{workload.kind} '{workload.name}' sets "
                        f"{', '.join(host_flags)} to true, breaking node "
                        f"isolation.{note}"
                    ),
                    fix="Remove hostNetwork/hostPID/hostIPC unless strictly required.",
                )
            )
            deductions += 15 if is_daemonset else 25

        # ── K007: hostPath volumes ────────────────────────────────────────────────
        # DaemonSets commonly need a hostPath mount to do their actual job (e.g. a
        # log/metrics collector reading /var/log) — still worth flagging, but as a
        # lighter-weight note rather than the same warning an arbitrary Deployment
        # doing this would earn. (`is_daemonset` computed above, for K006.)
        for volume in pod_spec.get("volumes") or []:
            if isinstance(volume, dict) and "hostPath" in volume:
                path = (volume.get("hostPath") or {}).get("path", "<unknown>")
                note = (
                    " Commonly required for node-level DaemonSets (log/metrics "
                    "collectors, CNI plugins) — verify this one actually needs it."
                    if is_daemonset
                    else ""
                )
                result.findings.append(
                    Finding(
                        rule_id="K007",
                        severity=Severity.info if is_daemonset else Severity.warning,
                        title="hostPath volume mounted",
                        description=(
                            f"{workload.kind} '{workload.name}' volume "
                            f"'{volume.get('name', '<unnamed>')}' mounts host path "
                            f"'{path}', breaking node isolation.{note}"
                        ),
                        fix="Use a PersistentVolumeClaim or emptyDir instead of hostPath.",
                    )
                )
                deductions += 5 if is_daemonset else 15

        # ── K012: ServiceAccount token automatically mounted ──────────────────────
        # Kubernetes defaults automountServiceAccountToken to true when unset, so a
        # workload silently gets a token it may not need. Standard CIS Benchmark
        # hardening check — WARN, since plenty of workloads do need the token.
        if pod_spec.get("automountServiceAccountToken") is not False:
            result.findings.append(
                Finding(
                    rule_id="K012",
                    severity=Severity.warning,
                    title="ServiceAccount token automatically mounted",
                    description=(
                        f"{workload.kind} '{workload.name}' does not set "
                        "automountServiceAccountToken: false. Kubernetes mounts "
                        "the token by default even if the workload never calls "
                        "the API server."
                    ),
                    fix="automountServiceAccountToken: false",
                )
            )
            deductions += 10

        for container, is_init in _containers(pod_spec):
            container_count += 1
            name = container.get("name", "<unnamed>")
            sec_ctx = _security_context(container)

            # ── K001: unpinned image ──────────────────────────────────────────────
            image = container.get("image", "")
            if image and _is_unpinned_image(image):
                result.findings.append(
                    Finding(
                        rule_id="K001",
                        severity=Severity.error,
                        title="Unpinned container image",
                        description=(
                            f"Container '{name}' image '{image}' uses ':latest' or has "
                            "no tag. Pin to a specific version or digest for "
                            "reproducible deploys."
                        ),
                        fix=_unpinned_fix(image),
                    )
                )
                deductions += 20

            # ── K002: privileged container ────────────────────────────────────────
            if sec_ctx.get("privileged") is True:
                result.findings.append(
                    Finding(
                        rule_id="K002",
                        severity=Severity.error,
                        title="Privileged container",
                        description=(
                            f"Container '{name}' runs with "
                            "securityContext.privileged: true."
                        ),
                        fix="Remove privileged: true; grant only the specific "
                        "capabilities the container actually needs.",
                    )
                )
                deductions += 30

            # ── K003: no runAsNonRoot ─────────────────────────────────────────────
            effective_non_root = sec_ctx.get(
                "runAsNonRoot", pod_security_context.get("runAsNonRoot")
            )
            if effective_non_root is not True:
                result.findings.append(
                    Finding(
                        rule_id="K003",
                        severity=Severity.error,
                        title="Container may run as root",
                        description=(
                            f"Container '{name}' has no runAsNonRoot: true set at "
                            "pod or container level."
                        ),
                        fix="securityContext:\n  runAsNonRoot: true",
                    )
                )
                deductions += 25

            # ── K013: missing or unsafe seccomp profile ───────────────────────────
            # A required component of the Restricted Pod Security Standard, same
            # container-then-pod fallback as K003's runAsNonRoot.
            effective_seccomp = (
                sec_ctx.get(
                    "seccompProfile", pod_security_context.get("seccompProfile")
                )
                or {}
            )
            if effective_seccomp.get("type") not in _SAFE_SECCOMP_TYPES:
                result.findings.append(
                    Finding(
                        rule_id="K013",
                        severity=Severity.warning,
                        title="Missing or unsafe seccomp profile",
                        description=(
                            f"Container '{name}' has no seccompProfile set to "
                            "RuntimeDefault or Localhost at pod or container level."
                        ),
                        fix="securityContext:\n  seccompProfile:\n    type: RuntimeDefault",
                    )
                )
                deductions += 10

            # ── K004: allowPrivilegeEscalation ────────────────────────────────────
            if sec_ctx.get("allowPrivilegeEscalation") is not False:
                result.findings.append(
                    Finding(
                        rule_id="K004",
                        severity=Severity.warning,
                        title="allowPrivilegeEscalation not disabled",
                        description=(
                            f"Container '{name}' does not explicitly set "
                            "allowPrivilegeEscalation: false."
                        ),
                        fix="securityContext:\n  allowPrivilegeEscalation: false",
                    )
                )
                deductions += 15

            # ── K005: missing resource requests/limits ────────────────────────────
            resources = container.get("resources") or {}
            if not resources.get("requests") or not resources.get("limits"):
                result.findings.append(
                    Finding(
                        rule_id="K005",
                        severity=Severity.warning,
                        title="Missing resource requests/limits",
                        description=(
                            f"Container '{name}' has no CPU/memory "
                            "resources.requests and/or resources.limits set."
                        ),
                        fix=(
                            "resources:\n  requests:\n    cpu: 100m\n"
                            "    memory: 128Mi\n  limits:\n    cpu: 250m\n"
                            "    memory: 256Mi"
                        ),
                    )
                )
                deductions += 10

            # ── K008: capabilities not minimized ──────────────────────────────────
            capabilities = sec_ctx.get("capabilities") or {}
            dropped = [str(c).upper() for c in (capabilities.get("drop") or [])]
            added = capabilities.get("add") or []
            if "ALL" not in dropped or added:
                result.findings.append(
                    Finding(
                        rule_id="K008",
                        severity=Severity.warning,
                        title="Linux capabilities not minimized",
                        description=(
                            f"Container '{name}' does not drop all capabilities"
                            + (f" and adds {added}" if added else "")
                            + "."
                        ),
                        fix='securityContext:\n  capabilities:\n    drop: ["ALL"]',
                    )
                )
                deductions += 10

            # ── K009: no health probes ──────────────────────────────────────────
            # Not applicable to init containers, or to run-to-completion workloads
            # (Job/CronJob) — they exit when done rather than serving requests, so
            # a liveness/readiness probe has nothing steady-state to check.
            if (
                not is_init
                and workload.kind not in _PROBE_EXEMPT_KINDS
                and not container.get("livenessProbe")
                and not container.get("readinessProbe")
            ):
                result.findings.append(
                    Finding(
                        rule_id="K009",
                        severity=Severity.info,
                        title="No health probes defined",
                        description=(
                            f"Container '{name}' has no livenessProbe or "
                            "readinessProbe."
                        ),
                        fix="Add livenessProbe/readinessProbe so Kubernetes can "
                        "detect and recover from failures.",
                    )
                )
                deductions += 5

            # ── K010: writable root filesystem ────────────────────────────────────
            if sec_ctx.get("readOnlyRootFilesystem") is not True:
                result.findings.append(
                    Finding(
                        rule_id="K010",
                        severity=Severity.info,
                        title="Root filesystem is writable",
                        description=(
                            f"Container '{name}' does not set "
                            "readOnlyRootFilesystem: true."
                        ),
                        fix="securityContext:\n  readOnlyRootFilesystem: true",
                    )
                )
                deductions += 10

            # ── K011: hardcoded secret in env value ───────────────────────────────
            # Only flags a literal `value:` matching a secret-like key name — a
            # `valueFrom.secretKeyRef`/`configMapKeyRef` reference is the correct
            # pattern and is never flagged.
            for env_var in container.get("env") or []:
                if not isinstance(env_var, dict):
                    continue
                env_name = env_var.get("name", "")
                if env_var.get("value") is not None and _SECRET_PATTERN.search(
                    env_name
                ):
                    result.findings.append(
                        Finding(
                            rule_id="K011",
                            severity=Severity.error,
                            title="Hardcoded secret in environment variable",
                            description=(
                                f"Container '{name}' sets env var '{env_name}' to a "
                                "literal value instead of referencing a Secret."
                            ),
                            fix=(
                                f"env:\n  - name: {env_name}\n    valueFrom:\n"
                                "      secretKeyRef:\n        name: <secret-name>\n"
                                "        key: <key>"
                            ),
                        )
                    )
                    deductions += 30

    result.score = max(0, 100 - deductions)
    result.metadata = {
        "workload_count": len(workloads),
        "workloads": [{"kind": w.kind, "name": w.name} for w in workloads],
        "container_count": container_count,
    }
    return result
