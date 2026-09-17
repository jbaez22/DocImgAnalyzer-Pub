# Kubernetes Workload Misconfiguration Scanner — Complete Test Cases

This document preserves the complete test-case content from the previous response, including the secure baseline manifests, scanner severity guidance, false-positive considerations, workload-specific exceptions, architecture guidance, and expected results.

Since these manifests are intended as **known-good test cases for a Kubernetes misconfiguration scanner**, the scanner should distinguish between:

| Classification | Meaning |
|---|---|
| **FAIL** | Security vulnerability, Kubernetes-invalid configuration, or strong Pod Security violation |
| **WARN** | Recommended production hardening, but legitimate exceptions exist |
| **INFO** | Operational/business recommendation or workload-specific choice |
| **PASS** | Configuration follows the expected secure pattern |

That distinction is important. For example, Kubernetes Restricted Pod Security requires `allowPrivilegeEscalation: false`, `runAsNonRoot: true`, an allowed seccomp profile, and dropping `ALL` capabilities. But `readOnlyRootFilesystem: true`, CPU limits, probes, explicit UID/GID, and disabling ServiceAccount token mounting are valuable hardening controls rather than universally mandatory settings.

Below are five manifests to use as the application's **secure baseline / PASS fixtures**.

---

# 1. StatefulSet — secure production baseline

A StatefulSet should normally be used when the workload needs persistent identity, storage, ordered operations, or stable network identity. Kubernetes currently recommends `ReadWriteOncePod` rather than `ReadWriteOnce` for production StatefulSet storage when supported by the storage environment.

```yaml
apiVersion: v1
kind: Service
metadata:
  name: secure-stateful-app
  namespace: production
  labels:
    app.kubernetes.io/name: secure-stateful-app
spec:
  clusterIP: None
  selector:
    app.kubernetes.io/name: secure-stateful-app
  ports:
    - name: http
      port: 8080
      targetPort: http

---
apiVersion: apps/v1
kind: StatefulSet
metadata:
  name: secure-stateful-app
  namespace: production
  labels:
    app.kubernetes.io/name: secure-stateful-app
    app.kubernetes.io/managed-by: kubectl
spec:
  serviceName: secure-stateful-app
  replicas: 3

  selector:
    matchLabels:
      app.kubernetes.io/name: secure-stateful-app

  podManagementPolicy: OrderedReady

  updateStrategy:
    type: RollingUpdate

  minReadySeconds: 10

  template:
    metadata:
      labels:
        app.kubernetes.io/name: secure-stateful-app
    spec:
      automountServiceAccountToken: false

      terminationGracePeriodSeconds: 30

      securityContext:
        runAsNonRoot: true
        runAsUser: 10001
        runAsGroup: 10001
        fsGroup: 10001
        seccompProfile:
          type: RuntimeDefault

      containers:
        - name: application

          # Example placeholder digest.
          # Replace with a real immutable image digest.
          image: example.com/application@sha256:aaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaa

          imagePullPolicy: IfNotPresent

          ports:
            - name: http
              containerPort: 8080
              protocol: TCP

          securityContext:
            allowPrivilegeEscalation: false
            privileged: false
            readOnlyRootFilesystem: true
            capabilities:
              drop:
                - ALL

          resources:
            requests:
              cpu: 100m
              memory: 128Mi
            limits:
              memory: 256Mi

          startupProbe:
            httpGet:
              path: /health/startup
              port: http
            failureThreshold: 30
            periodSeconds: 10

          readinessProbe:
            httpGet:
              path: /health/ready
              port: http
            initialDelaySeconds: 5
            periodSeconds: 10
            timeoutSeconds: 2
            failureThreshold: 3

          livenessProbe:
            httpGet:
              path: /health/live
              port: http
            periodSeconds: 20
            timeoutSeconds: 2
            failureThreshold: 3

          volumeMounts:
            - name: application-data
              mountPath: /var/lib/application

            - name: tmp
              mountPath: /tmp

      volumes:
        - name: tmp
          emptyDir: {}

  volumeClaimTemplates:
    - metadata:
        name: application-data
      spec:
        accessModes:
          - ReadWriteOncePod

        # Change for the actual cluster.
        storageClassName: standard

        resources:
          requests:
            storage: 10Gi
```

## What your scanner should detect

| Check | Severity |
|---|---|
| Selector does not match template labels | **FAIL** |
| `privileged: true` | **FAIL** |
| `allowPrivilegeEscalation: true` | **FAIL** |
| `runAsNonRoot: false` | **FAIL** |
| capabilities not dropping `ALL` under Restricted policy | **FAIL** |
| Missing/unsafe seccomp under Restricted policy | **FAIL** |
| `hostNetwork`, `hostPID`, `hostIPC` unnecessarily enabled | **FAIL/WARN** |
| Missing memory request/limit | **WARN** |
| Missing CPU request | **WARN** |
| Missing CPU limit | **INFO/WARN**, not FAIL |
| Image uses `:latest` | **WARN** |
| Image not pinned by digest | **WARN** |
| Missing probes | **WARN** |
| ServiceAccount token automatically mounted unnecessarily | **WARN** |
| `readOnlyRootFilesystem: false` | **WARN** |
| StatefulSet uses `ReadWriteOnce` instead of `ReadWriteOncePod` | **INFO/WARN** |
| No persistent storage | **INFO**, not necessarily wrong |
| replicas = 1 | **INFO**, not security problem |

Don't require `volumeClaimTemplates`: a StatefulSet may legitimately be used for stable identities without persistent volumes. Kubernetes explicitly lists several valid StatefulSet use cases beyond storage.

---

# 2. DaemonSet — secure baseline

DaemonSets deserve special treatment in your scanner because legitimate DaemonSets commonly need node-level access. Log collectors, CNI components, monitoring agents, storage agents, and security software may legitimately use `hostPath`, tolerations, host networking, capabilities, or elevated privileges. Kubernetes itself shows node log collection using a `hostPath`.

```yaml
apiVersion: apps/v1
kind: DaemonSet
metadata:
  name: secure-node-agent
  namespace: monitoring
  labels:
    app.kubernetes.io/name: secure-node-agent

spec:
  selector:
    matchLabels:
      app.kubernetes.io/name: secure-node-agent

  updateStrategy:
    type: RollingUpdate
    rollingUpdate:
      maxUnavailable: 1

  template:
    metadata:
      labels:
        app.kubernetes.io/name: secure-node-agent

    spec:
      automountServiceAccountToken: false

      terminationGracePeriodSeconds: 30

      securityContext:
        runAsNonRoot: true
        runAsUser: 10001
        runAsGroup: 10001
        seccompProfile:
          type: RuntimeDefault

      containers:
        - name: node-agent

          image: example.com/node-agent@sha256:bbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbb

          securityContext:
            privileged: false
            allowPrivilegeEscalation: false
            readOnlyRootFilesystem: true
            capabilities:
              drop:
                - ALL

          resources:
            requests:
              cpu: 50m
              memory: 64Mi
            limits:
              memory: 128Mi

          readinessProbe:
            exec:
              command:
                - /bin/agent
                - health
            periodSeconds: 10
            timeoutSeconds: 2

          livenessProbe:
            exec:
              command:
                - /bin/agent
                - health
            periodSeconds: 30
            timeoutSeconds: 2

          volumeMounts:
            - name: tmp
              mountPath: /tmp

      volumes:
        - name: tmp
          emptyDir: {}
```

Notice that the secure generic fixture intentionally does **not** contain:

```yaml
hostNetwork: true
hostPID: true
hostPath:
privileged: true
```

However, these should **not automatically mean a broken DaemonSet**.

For example:

```yaml
volumes:
  - name: logs
    hostPath:
      path: /var/log
      type: Directory
```

is completely reasonable for a node log collector.

Your scanner should therefore report something such as:

> **HIGH: hostPath grants access to host filesystem. Verify that node filesystem access is required for this DaemonSet.**

rather than:

> **ERROR: DaemonSet is insecure.**

This is one of the biggest areas where Kubernetes scanners produce false positives.

---

# 3. Job — secure baseline

Jobs are different from long-running workloads. Their Pod restart policy can only be `Never` or `OnFailure`. Kubernetes also supports `ttlSecondsAfterFinished` to automatically clean up completed Jobs.

```yaml
apiVersion: batch/v1
kind: Job
metadata:
  name: secure-data-processing
  namespace: production
  labels:
    app.kubernetes.io/name: secure-data-processing

spec:
  backoffLimit: 3

  activeDeadlineSeconds: 1800

  ttlSecondsAfterFinished: 3600

  template:
    metadata:
      labels:
        app.kubernetes.io/name: secure-data-processing

    spec:
      restartPolicy: Never

      automountServiceAccountToken: false

      securityContext:
        runAsNonRoot: true
        runAsUser: 10001
        runAsGroup: 10001
        seccompProfile:
          type: RuntimeDefault

      containers:
        - name: processor

          image: example.com/data-processor@sha256:cccccccccccccccccccccccccccccccccccccccccccccccccccccccccccccccc

          securityContext:
            privileged: false
            allowPrivilegeEscalation: false
            readOnlyRootFilesystem: true
            capabilities:
              drop:
                - ALL

          resources:
            requests:
              cpu: 100m
              memory: 128Mi
            limits:
              memory: 256Mi

          volumeMounts:
            - name: tmp
              mountPath: /tmp

      volumes:
        - name: tmp
          emptyDir:
            sizeLimit: 256Mi
```

## Job-specific scanner logic

| Configuration | Result |
|---|---|
| `restartPolicy: Always` | **FAIL** |
| `restartPolicy: Never` | **PASS** |
| `restartPolicy: OnFailure` | **PASS** |
| Missing `backoffLimit` | **INFO/WARN** |
| Very large `backoffLimit` | **WARN** |
| Missing `activeDeadlineSeconds` | **WARN** |
| Missing `ttlSecondsAfterFinished` | **INFO/WARN** |
| Missing liveness probe | **PASS / ignore** |
| Missing readiness probe | **PASS / ignore** |
| Missing startup probe | **PASS / ignore** |

### Don't require probes on Jobs

Your scanner should **not** report:

> Job does not have a liveness probe.

Batch Jobs often execute a command and exit. A liveness or readiness probe is usually unnecessary and could actually be inappropriate.

---

# 4. ReplicaSet — secure baseline

```yaml
apiVersion: apps/v1
kind: ReplicaSet
metadata:
  name: secure-web
  namespace: production
  labels:
    app.kubernetes.io/name: secure-web

spec:
  replicas: 3

  selector:
    matchLabels:
      app.kubernetes.io/name: secure-web

  template:
    metadata:
      labels:
        app.kubernetes.io/name: secure-web

    spec:
      automountServiceAccountToken: false

      terminationGracePeriodSeconds: 30

      securityContext:
        runAsNonRoot: true
        runAsUser: 10001
        runAsGroup: 10001
        seccompProfile:
          type: RuntimeDefault

      containers:
        - name: web

          image: example.com/web@sha256:dddddddddddddddddddddddddddddddddddddddddddddddddddddddddddddddd

          ports:
            - name: http
              containerPort: 8080

          securityContext:
            privileged: false
            allowPrivilegeEscalation: false
            readOnlyRootFilesystem: true
            capabilities:
              drop:
                - ALL

          resources:
            requests:
              cpu: 100m
              memory: 128Mi
            limits:
              memory: 256Mi

          startupProbe:
            httpGet:
              path: /health/startup
              port: http
            failureThreshold: 30
            periodSeconds: 5

          readinessProbe:
            httpGet:
              path: /health/ready
              port: http
            periodSeconds: 10

          livenessProbe:
            httpGet:
              path: /health/live
              port: http
            periodSeconds: 30

          volumeMounts:
            - name: tmp
              mountPath: /tmp

      volumes:
        - name: tmp
          emptyDir: {}
```

There is one special scanner rule here:

### Do NOT classify a ReplicaSet itself as a misconfiguration.

ReplicaSets are perfectly valid Kubernetes objects.

However, Kubernetes recommends using a **Deployment rather than directly managing ReplicaSets** for normal stateless applications because Deployments provide controlled updates, rollbacks, and lifecycle management.

So:

```text
Direct ReplicaSet detected
```

should be:

**INFO**

or at most:

**LOW / WARN**

not HIGH or FAIL.

Even more importantly, if your scanner scans a live cluster and sees:

```yaml
metadata:
  ownerReferences:
    - kind: Deployment
```

do **not** produce that warning at all. That ReplicaSet is being correctly managed by a Deployment.

---

# 5. CronJob — secure production baseline

```yaml
apiVersion: batch/v1
kind: CronJob
metadata:
  name: secure-daily-report
  namespace: production
  labels:
    app.kubernetes.io/name: secure-daily-report

spec:
  schedule: "0 2 * * *"

  timeZone: "Etc/UTC"

  concurrencyPolicy: Forbid

  startingDeadlineSeconds: 300

  successfulJobsHistoryLimit: 3
  failedJobsHistoryLimit: 3

  jobTemplate:
    spec:

      backoffLimit: 3

      activeDeadlineSeconds: 1800

      ttlSecondsAfterFinished: 3600

      template:
        metadata:
          labels:
            app.kubernetes.io/name: secure-daily-report

        spec:
          restartPolicy: Never

          automountServiceAccountToken: false

          securityContext:
            runAsNonRoot: true
            runAsUser: 10001
            runAsGroup: 10001
            seccompProfile:
              type: RuntimeDefault

          containers:
            - name: report

              image: example.com/report@sha256:eeeeeeeeeeeeeeeeeeeeeeeeeeeeeeeeeeeeeeeeeeeeeeeeeeeeeeeeeeeeeeee

              securityContext:
                privileged: false
                allowPrivilegeEscalation: false
                readOnlyRootFilesystem: true
                capabilities:
                  drop:
                    - ALL

              resources:
                requests:
                  cpu: 100m
                  memory: 128Mi
                limits:
                  memory: 256Mi

              volumeMounts:
                - name: tmp
                  mountPath: /tmp

          volumes:
            - name: tmp
              emptyDir:
                sizeLimit: 256Mi
```

CronJob configuration is another place where scanners can easily produce bad results.

Kubernetes supports `Allow`, `Forbid`, and `Replace` concurrency policies; `Allow` is the default. `startingDeadlineSeconds`, history limits, and `timeZone` are all optional fields.

Therefore:

| CronJob configuration | Scanner result |
|---|---|
| `concurrencyPolicy: Forbid` | PASS |
| `concurrencyPolicy: Replace` | PASS |
| `concurrencyPolicy: Allow` | **INFO/WARN**, not FAIL |
| `concurrencyPolicy` missing | **WARN** because implicit Allow |
| Missing `startingDeadlineSeconds` | WARN |
| Missing `successfulJobsHistoryLimit` | INFO |
| Missing `failedJobsHistoryLimit` | INFO |
| Missing `timeZone` | INFO |
| Invalid cron schedule | FAIL |
| Job restartPolicy = Always | FAIL |
| No probes | PASS |

Whether `Forbid`, `Replace`, or `Allow` is best is a **business/application decision**.

For example, a database backup probably should use:

```yaml
concurrencyPolicy: Forbid
```

while a lightweight telemetry collection task might safely use:

```yaml
concurrencyPolicy: Allow
```

Your scanner should understand that distinction.

---

# The baseline security block

For the Pod-owning workloads listed above, this is the most useful generic security baseline:

```yaml
spec:
  automountServiceAccountToken: false

  securityContext:
    runAsNonRoot: true
    seccompProfile:
      type: RuntimeDefault

  containers:
    - name: app

      securityContext:
        allowPrivilegeEscalation: false
        privileged: false
        readOnlyRootFilesystem: true
        capabilities:
          drop:
            - ALL
```

The Restricted Pod Security Standard particularly supports controls such as non-root execution, preventing privilege escalation, dropping capabilities, and using seccomp. Kubernetes recommends enforcing Pod Security Standards and using least privilege.

But your scanner should differentiate **Restricted compliance** from your additional hardening policy.

---

# Recommended scanner severity model

This is probably the most important part for the application.

| Rule | Suggested severity |
|---|---|
| `privileged: true` | 🔴 CRITICAL |
| `hostPID: true` | 🔴 HIGH |
| `hostIPC: true` | 🔴 HIGH |
| `hostNetwork: true` | 🟠 HIGH/WARN |
| dangerous `hostPath` such as `/`, `/etc`, `/proc`, `/sys`, container runtime socket | 🔴 CRITICAL/HIGH |
| Docker/containerd socket mounted | 🔴 CRITICAL |
| `allowPrivilegeEscalation: true` | 🔴 HIGH |
| `runAsNonRoot: false` | 🔴 HIGH |
| UID 0 explicitly configured | 🔴 HIGH |
| seccomp `Unconfined` | 🔴 HIGH |
| capabilities added such as `SYS_ADMIN` | 🔴 HIGH |
| capabilities don't drop `ALL` | 🟠 HIGH/WARN |
| `readOnlyRootFilesystem` missing/false | 🟡 WARN |
| mutable `latest` tag | 🟠 WARN |
| image tag but no digest | 🟡 WARN |
| resources completely missing | 🟠 WARN |
| memory request missing | 🟡 WARN |
| memory limit missing | 🟠 WARN |
| CPU request missing | 🟡 WARN |
| CPU limit missing | 🔵 INFO/WARN |
| ServiceAccount token automatically mounted | 🟡 WARN |
| no NetworkPolicy found | 🟡 WARN |
| Secret placed directly in environment value | 🔴 HIGH |
| plaintext password/API key in manifest | 🔴 CRITICAL |
| readiness probe missing for server workload | 🟡 WARN |
| liveness probe missing for server workload | 🟡 WARN |
| Job/CronJob probes missing | ✅ IGNORE |
| CronJob concurrencyPolicy missing | 🟡 WARN |
| CronJob `Allow` | 🔵 INFO |
| Job has no execution deadline | 🟡 WARN |
| Job has no TTL | 🔵 INFO |
| direct ReplicaSet | 🔵 INFO |
| StatefulSet lacks PVC | 🔵 INFO |
| DaemonSet uses hostPath | 🟠 CONTEXTUAL |
| DaemonSet uses hostNetwork | 🟠 CONTEXTUAL |
| DaemonSet privileged | 🔴 HIGH but CONTEXTUAL |

Kubernetes itself points out that some system and infrastructure workloads legitimately need elevated permissions, so a scanner should surface the risk without blindly declaring every exception invalid.

---

# A very important design decision for your scanner

The engine should evaluate rules in **three layers**:

```text
Kubernetes Manifest
       │
       ▼
┌─────────────────────────────┐
│ 1. Kubernetes Validity      │
│                             │
│ API version                 │
│ required fields             │
│ selector/labels             │
│ restartPolicy               │
│ schema                      │
└──────────────┬──────────────┘
               │
               ▼
┌─────────────────────────────┐
│ 2. Security / PSS           │
│                             │
│ root                        │
│ privileged                  │
│ capabilities                │
│ seccomp                     │
│ host access                 │
│ privilege escalation        │
└──────────────┬──────────────┘
               │
               ▼
┌─────────────────────────────┐
│ 3. Production Best Practice │
│                             │
│ resources                   │
│ probes                      │
│ immutable images            │
│ deadlines                   │
│ cleanup                     │
│ availability                │
└─────────────────────────────┘
```

That lets the output say something much more accurate, such as:

```text
Kubernetes validation:     PASS
Pod Security Restricted:   PASS
Production hardening:      2 WARNINGS
Operational guidance:      1 INFO
```

instead of simply:

```text
FAILED — 3 misconfigurations
```

That design will substantially reduce false positives.

One more nuance: Kubernetes' security checklist recommends resource constraints, but it says memory limits should be set while CPU limits **might** be appropriate for sensitive workloads. That is a good reason not to make `"CPU limit missing"` a hard failure.

---

# Known-good expected results

These five fixtures should produce:

```text
StatefulSet
Security: PASS
Kubernetes validity: PASS
Best practices: PASS

DaemonSet
Security: PASS
Kubernetes validity: PASS
Best practices: PASS

Job
Security: PASS
Kubernetes validity: PASS
Best practices: PASS

ReplicaSet
Security: PASS
Kubernetes validity: PASS
Best practices:
  INFO: Direct ReplicaSet management.
        Deployment is normally preferred.

CronJob
Security: PASS
Kubernetes validity: PASS
Best practices: PASS
```

The `sha256:aaaa...`, `bbbb...`, etc. values above are deliberately **test placeholders**, not real image digests. For actual deployment, substitute valid immutable image digests. For static-analysis fixtures, they are useful because the scanner can recognize the correct `repository@sha256:<digest>` structure without depending on an external registry.

---

# Recommended next rule-catalog structure

A useful next step for the detection engine is to define a formal rule catalog, for example:

```text
K8S-SEC-001 privileged container
K8S-SEC-002 root container
K8S-BP-001 missing resources
```

Each rule should contain:

- Unique rule ID
- Rule name
- Description
- Category
- Severity
- Exact YAML path or paths inspected
- Kubernetes workload types to which the rule applies
- Workload-specific exceptions
- Pod Security Standard relationship
- Whether the rule is Kubernetes validity, security, hardening, or operational guidance
- PASS test manifest
- FAIL test manifest
- WARN test manifest where applicable
- False-positive considerations
- Remediation guidance
- References to the relevant Kubernetes documentation

This structure provides a strong unit-test dataset and directly addresses the false-positive problem.

---

# Reference documentation

The guidance in this test set is based on Kubernetes documentation covering:

- Pod Security Standards
- Enforcing Pod Security Standards
- Kubernetes Security Checklist
- StatefulSets
- DaemonSets
- Jobs
- ReplicaSets
- CronJobs

Useful official Kubernetes documentation paths:

- `kubernetes.io/docs/concepts/security/pod-security-standards/`
- `kubernetes.io/docs/setup/best-practices/enforcing-pod-security-standards/`
- `kubernetes.io/docs/concepts/security/security-checklist/`
- `kubernetes.io/docs/concepts/workloads/controllers/statefulset/`
- `kubernetes.io/docs/concepts/workloads/controllers/daemonset/`
- `kubernetes.io/docs/concepts/workloads/controllers/job/`
- `kubernetes.io/docs/concepts/workloads/controllers/replicaset/`
- `kubernetes.io/docs/concepts/workloads/controllers/cron-jobs/`

---

## Purpose of this file

This file is intended to serve as a baseline for testing a Kubernetes configuration/misconfiguration scanner.

The key principle is:

> **Do not treat every deviation from a production recommendation as a security failure.**

The scanner should distinguish Kubernetes validity, security requirements, production hardening, and contextual operational guidance. Workload-aware exceptions are especially important for Jobs, CronJobs, DaemonSets, StatefulSets, and ReplicaSets to avoid false positives.
