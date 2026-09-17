# Kubernetes Workload Misconfiguration Scanner — Intentionally Bad Test Cases

> **WARNING:** Every manifest in this document is intentionally insecure, incomplete, risky, or contrary to production best practices. These examples are designed for testing a Kubernetes misconfiguration scanner. **Do not deploy them in production.**

The examples correspond to the same workload types used in the secure baseline:

1. StatefulSet
2. DaemonSet
3. Job
4. ReplicaSet
5. CronJob

The goal is not merely to make invalid YAML. Most examples remain structurally plausible so a scanner can detect meaningful security and operational problems rather than only schema errors.

## Expected classification model

| Classification | Meaning |
|---|---|
| **FAIL** | Security vulnerability, Kubernetes-invalid configuration, or strong Pod Security violation |
| **WARN** | Production hardening problem where legitimate exceptions may exist |
| **INFO** | Operational/business recommendation or workload-specific choice |
| **PASS** | Configuration follows the expected secure pattern |

---

# 1. StatefulSet — intentionally bad example

```yaml
apiVersion: v1
kind: Service
metadata:
  name: insecure-stateful-app
  namespace: production
spec:
  clusterIP: None
  selector:
    app: insecure-stateful-app
  ports:
    - port: 8080
      targetPort: 8080

---
apiVersion: apps/v1
kind: StatefulSet
metadata:
  name: insecure-stateful-app
  namespace: production
spec:
  serviceName: insecure-stateful-app
  replicas: 1

  selector:
    matchLabels:
      app: insecure-stateful-app

  template:
    metadata:
      labels:
        app: insecure-stateful-app

    spec:
      # Token is unnecessarily available to the workload.
      automountServiceAccountToken: true

      # Host namespace access substantially increases impact of compromise.
      hostNetwork: true
      hostPID: true
      hostIPC: true

      containers:
        - name: application

          # Mutable image tag.
          image: example.com/application:latest
          imagePullPolicy: Always

          ports:
            - containerPort: 8080

          securityContext:
            privileged: true
            allowPrivilegeEscalation: true
            readOnlyRootFilesystem: false
            runAsNonRoot: false
            runAsUser: 0

            capabilities:
              add:
                - SYS_ADMIN
                - NET_ADMIN

          # No CPU/memory requests or limits.

          # No startupProbe.
          # No readinessProbe.
          # No livenessProbe.

          env:
            # Intentionally hard-coded secret.
            - name: DATABASE_PASSWORD
              value: "SuperSecretPassword123"

          volumeMounts:
            - name: host-root
              mountPath: /host

            - name: application-data
              mountPath: /var/lib/application

      volumes:
        - name: host-root
          hostPath:
            path: /
            type: Directory

  volumeClaimTemplates:
    - metadata:
        name: application-data
      spec:
        accessModes:
          - ReadWriteOnce
        resources:
          requests:
            storage: 1Gi
```

## Expected StatefulSet findings

| Finding | Expected result |
|---|---|
| `automountServiceAccountToken: true` without demonstrated need | WARN |
| `hostNetwork: true` | HIGH/WARN |
| `hostPID: true` | HIGH |
| `hostIPC: true` | HIGH |
| `privileged: true` | CRITICAL |
| `allowPrivilegeEscalation: true` | HIGH |
| `runAsNonRoot: false` | HIGH |
| `runAsUser: 0` | HIGH |
| `readOnlyRootFilesystem: false` | WARN |
| `SYS_ADMIN` capability | HIGH/CRITICAL |
| `NET_ADMIN` capability | HIGH |
| Does not drop `ALL` capabilities | HIGH/WARN |
| Missing safe seccomp profile | HIGH under Restricted PSS |
| Image uses `:latest` | WARN |
| Image not pinned by digest | WARN |
| Missing resource requests | WARN |
| Missing memory limit | WARN |
| Missing CPU request | WARN |
| Missing CPU limit | INFO/WARN |
| Missing startup/readiness/liveness probes for server workload | WARN |
| Plaintext database password | CRITICAL |
| Host root `/` mounted with `hostPath` | CRITICAL |
| StatefulSet uses `ReadWriteOnce` rather than `ReadWriteOncePod` | INFO/WARN |
| `replicas: 1` | INFO |

### False-positive considerations

`replicas: 1` is not a security failure. `ReadWriteOnce` may be required by a storage platform that does not support `ReadWriteOncePod`. The scanner should not convert those findings into critical security failures.

---

# 2. DaemonSet — intentionally bad example

DaemonSets require particularly careful context handling because legitimate node agents may need host access. This example deliberately combines several dangerous settings.

```yaml
apiVersion: apps/v1
kind: DaemonSet
metadata:
  name: insecure-node-agent
  namespace: monitoring
spec:
  selector:
    matchLabels:
      app: insecure-node-agent

  template:
    metadata:
      labels:
        app: insecure-node-agent

    spec:
      automountServiceAccountToken: true

      hostNetwork: true
      hostPID: true
      hostIPC: true

      containers:
        - name: node-agent

          image: example.com/node-agent:latest

          securityContext:
            privileged: true
            allowPrivilegeEscalation: true
            readOnlyRootFilesystem: false
            runAsUser: 0
            runAsNonRoot: false

            capabilities:
              add:
                - SYS_ADMIN
                - NET_ADMIN
                - SYS_PTRACE

          # No resources.
          # No probes.

          volumeMounts:
            - name: host-root
              mountPath: /host

            - name: proc
              mountPath: /host-proc

            - name: docker-socket
              mountPath: /var/run/docker.sock

      volumes:
        - name: host-root
          hostPath:
            path: /
            type: Directory

        - name: proc
          hostPath:
            path: /proc
            type: Directory

        - name: docker-socket
          hostPath:
            path: /var/run/docker.sock
            type: Socket
```

## Expected DaemonSet findings

| Finding | Expected result |
|---|---|
| `privileged: true` | HIGH, but contextual for DaemonSets |
| `hostPID: true` | HIGH/contextual |
| `hostIPC: true` | HIGH/contextual |
| `hostNetwork: true` | HIGH/WARN/contextual |
| Host `/` mounted | CRITICAL |
| `/proc` mounted | HIGH/CRITICAL |
| Docker socket mounted | CRITICAL |
| `runAsUser: 0` | HIGH |
| `runAsNonRoot: false` | HIGH |
| `allowPrivilegeEscalation: true` | HIGH |
| `SYS_ADMIN` | HIGH/CRITICAL |
| `NET_ADMIN` | HIGH/contextual |
| `SYS_PTRACE` | HIGH |
| Missing `capabilities.drop: [ALL]` | HIGH/WARN |
| Missing seccomp | HIGH under Restricted PSS |
| `readOnlyRootFilesystem: false` | WARN |
| Mutable `latest` image | WARN |
| Missing resource requests/limits | WARN |
| Missing probes for long-running agent | WARN |
| Automatic ServiceAccount token | WARN |

## Critical false-positive rule for DaemonSets

Do **not** blindly implement:

```text
if kind == DaemonSet and hostPath exists:
    FAIL
```

That will generate many false positives.

Instead, evaluate the path and access level.

For example:

```yaml
hostPath:
  path: /var/log
```

may be legitimate for a logging agent.

But:

```yaml
hostPath:
  path: /
```

or:

```yaml
hostPath:
  path: /var/run/docker.sock
```

should receive much higher severity.

A useful model is:

| hostPath | Suggested severity |
|---|---|
| `/var/log` read-only | WARN / contextual |
| `/etc` | HIGH |
| `/proc` | HIGH |
| `/sys` | HIGH |
| `/` | CRITICAL |
| Docker socket | CRITICAL |
| containerd socket | CRITICAL |
| CRI-O socket | CRITICAL |

---

# 3. Job — intentionally bad example

This Job demonstrates poor security and batch-processing practices while keeping the Pod restart policy valid enough for meaningful scanner testing.

```yaml
apiVersion: batch/v1
kind: Job
metadata:
  name: insecure-data-processing
  namespace: production
spec:
  # Excessive retries may cause runaway workload behavior.
  backoffLimit: 100

  # No activeDeadlineSeconds.
  # No ttlSecondsAfterFinished.

  template:
    metadata:
      labels:
        app: insecure-data-processing

    spec:
      restartPolicy: OnFailure

      automountServiceAccountToken: true

      containers:
        - name: processor

          image: example.com/data-processor:latest

          securityContext:
            privileged: true
            allowPrivilegeEscalation: true
            readOnlyRootFilesystem: false
            runAsNonRoot: false
            runAsUser: 0

            capabilities:
              add:
                - SYS_ADMIN

          env:
            - name: API_KEY
              value: "production-api-key-123456"

          # No resource requests.
          # No resource limits.

          volumeMounts:
            - name: host-data
              mountPath: /host-data

      volumes:
        - name: host-data
          hostPath:
            path: /
            type: Directory
```

## Expected Job findings

| Finding | Expected result |
|---|---|
| `restartPolicy: OnFailure` | PASS |
| Very high `backoffLimit` | WARN |
| Missing `activeDeadlineSeconds` | WARN |
| Missing `ttlSecondsAfterFinished` | INFO/WARN |
| `automountServiceAccountToken: true` | WARN |
| `privileged: true` | CRITICAL |
| `allowPrivilegeEscalation: true` | HIGH |
| root execution | HIGH |
| `SYS_ADMIN` | HIGH/CRITICAL |
| Missing capability drop | HIGH/WARN |
| Missing seccomp | HIGH under Restricted PSS |
| Writable root filesystem | WARN |
| Mutable image | WARN |
| Plaintext API key | CRITICAL |
| Missing resources | WARN |
| Host root mounted | CRITICAL |
| No probes | PASS / IGNORE |

### Important Job false-positive tests

The following must **not** be considered errors:

```yaml
restartPolicy: Never
```

and:

```yaml
restartPolicy: OnFailure
```

Both are legitimate for Jobs.

Also do not require:

```yaml
livenessProbe:
readinessProbe:
startupProbe:
```

for normal finite batch Jobs.

### Separate invalid Job schema test

A useful negative validation fixture is:

```yaml
apiVersion: batch/v1
kind: Job
metadata:
  name: invalid-job-restart-policy
spec:
  template:
    spec:
      restartPolicy: Always
      containers:
        - name: test
          image: busybox:latest
          command:
            - /bin/sh
            - -c
            - echo test
```

Expected:

```text
Kubernetes validity: FAIL
Reason: Job Pod template restartPolicy must be Never or OnFailure.
```

---

# 4. ReplicaSet — intentionally bad example

```yaml
apiVersion: apps/v1
kind: ReplicaSet
metadata:
  name: insecure-web
  namespace: production

spec:
  replicas: 1

  selector:
    matchLabels:
      app: insecure-web

  template:
    metadata:
      labels:
        app: insecure-web

    spec:
      automountServiceAccountToken: true

      hostNetwork: true

      containers:
        - name: web

          image: example.com/web:latest

          ports:
            - containerPort: 80

          securityContext:
            privileged: true
            allowPrivilegeEscalation: true
            readOnlyRootFilesystem: false
            runAsNonRoot: false
            runAsUser: 0

            capabilities:
              add:
                - NET_ADMIN
                - SYS_ADMIN

          env:
            - name: ADMIN_PASSWORD
              value: "AdminPassword123"

          # No resources.
          # No startup probe.
          # No readiness probe.
          # No liveness probe.

          volumeMounts:
            - name: host-etc
              mountPath: /host-etc

      volumes:
        - name: host-etc
          hostPath:
            path: /etc
            type: Directory
```

## Expected ReplicaSet findings

| Finding | Expected result |
|---|---|
| Direct ReplicaSet | INFO, not security FAIL |
| `replicas: 1` | INFO |
| ServiceAccount token mounted | WARN |
| `hostNetwork: true` | HIGH/WARN |
| Mutable `latest` image | WARN |
| `privileged: true` | CRITICAL |
| privilege escalation | HIGH |
| root execution | HIGH |
| writable root filesystem | WARN |
| dangerous capabilities | HIGH/CRITICAL |
| missing `drop: ALL` | HIGH/WARN |
| missing seccomp | HIGH under Restricted PSS |
| plaintext admin password | CRITICAL |
| no resources | WARN |
| no probes for web workload | WARN |
| `/etc` hostPath | HIGH |

## ReplicaSet ownership false-positive test

A scanner operating against live Kubernetes objects may encounter:

```yaml
metadata:
  ownerReferences:
    - apiVersion: apps/v1
      kind: Deployment
      name: secure-web
      controller: true
```

If that exists, suppress:

```text
INFO: Direct ReplicaSet management
```

because the ReplicaSet is managed by a Deployment.

Do **not** suppress security findings inside the ReplicaSet Pod template. A Deployment-managed ReplicaSet can still contain insecure containers.

---

# 5. CronJob — intentionally bad example

```yaml
apiVersion: batch/v1
kind: CronJob
metadata:
  name: insecure-daily-report
  namespace: production

spec:
  schedule: "* * * * *"

  # Explicit Allow can cause overlapping executions.
  # This is contextual, not automatically invalid.
  concurrencyPolicy: Allow

  # No startingDeadlineSeconds.
  # No timeZone.

  successfulJobsHistoryLimit: 100
  failedJobsHistoryLimit: 100

  jobTemplate:
    spec:
      backoffLimit: 50

      # No activeDeadlineSeconds.
      # No ttlSecondsAfterFinished.

      template:
        metadata:
          labels:
            app: insecure-daily-report

        spec:
          restartPolicy: OnFailure

          automountServiceAccountToken: true

          containers:
            - name: report

              image: example.com/report:latest

              securityContext:
                privileged: true
                allowPrivilegeEscalation: true
                readOnlyRootFilesystem: false
                runAsNonRoot: false
                runAsUser: 0

                capabilities:
                  add:
                    - SYS_ADMIN

              env:
                - name: REPORT_DB_PASSWORD
                  value: "ReportDBPassword123"

              # No resources.

              volumeMounts:
                - name: host-root
                  mountPath: /host

          volumes:
            - name: host-root
              hostPath:
                path: /
                type: Directory
```

## Expected CronJob findings

| Finding | Expected result |
|---|---|
| Every-minute schedule | INFO/WARN depending policy |
| `concurrencyPolicy: Allow` | INFO/WARN, not FAIL |
| Missing `startingDeadlineSeconds` | WARN |
| Missing `timeZone` | INFO |
| Very high successful history | INFO/WARN |
| Very high failed history | INFO/WARN |
| High `backoffLimit` | WARN |
| Missing `activeDeadlineSeconds` | WARN |
| Missing TTL | INFO/WARN |
| `restartPolicy: OnFailure` | PASS |
| ServiceAccount token mounted | WARN |
| `privileged: true` | CRITICAL |
| privilege escalation | HIGH |
| root execution | HIGH |
| missing seccomp | HIGH under Restricted PSS |
| dangerous capability | HIGH/CRITICAL |
| writable root filesystem | WARN |
| mutable image | WARN |
| plaintext password | CRITICAL |
| no resources | WARN |
| host `/` mounted | CRITICAL |
| no probes | PASS / IGNORE |

## CronJob false-positive considerations

The schedule:

```yaml
schedule: "* * * * *"
```

is valid. Running every minute may be exactly what an application requires.

Therefore this should not be:

```text
FAIL: CronJob runs too frequently
```

A better result is:

```text
INFO/WARN: CronJob executes every minute.
Review workload duration and concurrency behavior to ensure executions do not overlap or create excessive load.
```

Similarly:

```yaml
concurrencyPolicy: Allow
```

is a valid Kubernetes setting.

It becomes risky when the workload cannot safely overlap.

---

# 6. Cross-workload intentionally bad security block

This is a compact reusable negative fixture for Pod-owning workload templates.

```yaml
spec:
  automountServiceAccountToken: true

  hostNetwork: true
  hostPID: true
  hostIPC: true

  containers:
    - name: app
      image: example.com/app:latest

      securityContext:
        privileged: true
        allowPrivilegeEscalation: true
        readOnlyRootFilesystem: false
        runAsNonRoot: false
        runAsUser: 0

        capabilities:
          add:
            - SYS_ADMIN
            - NET_ADMIN

      env:
        - name: PASSWORD
          value: "plaintext-password"

      volumeMounts:
        - name: host-root
          mountPath: /host

  volumes:
    - name: host-root
      hostPath:
        path: /
        type: Directory
```

A scanner should produce multiple independent findings rather than one generic "insecure workload" result.

Expected categories include:

```text
CRITICAL  Privileged container
HIGH      Privilege escalation allowed
HIGH      Container explicitly runs as UID 0
HIGH      Container is allowed to run as root
HIGH      hostPID enabled
HIGH      hostIPC enabled
HIGH/WARN hostNetwork enabled
CRITICAL  Host root filesystem mounted
HIGH      SYS_ADMIN capability
HIGH      NET_ADMIN capability
HIGH/WARN ALL capabilities not dropped
HIGH      Restricted seccomp requirement not satisfied
WARN      Root filesystem writable
WARN      ServiceAccount token automatically mounted
WARN      Mutable image tag
WARN      Image not digest-pinned
CRITICAL  Plaintext credential
```

---

# 7. Rules that should NOT blindly generate failures

These are especially important for false-positive testing.

| Condition | Incorrect behavior | Better behavior |
|---|---|---|
| CPU limit missing | FAIL | INFO/WARN |
| StatefulSet has no PVC | FAIL | INFO |
| StatefulSet replicas = 1 | FAIL | INFO |
| DaemonSet uses `hostPath` | Always FAIL | Contextual risk evaluation |
| DaemonSet uses host networking | Always FAIL | HIGH/WARN with workload context |
| DaemonSet privileged | Ignore | HIGH risk but allow documented exception |
| Job has no probes | WARN/FAIL | IGNORE |
| CronJob has no probes | WARN/FAIL | IGNORE |
| Job uses `OnFailure` | FAIL | PASS |
| Job uses `Never` | FAIL | PASS |
| CronJob uses `Allow` | FAIL | INFO/WARN |
| CronJob uses `Replace` | FAIL | PASS/contextual |
| CronJob missing `timeZone` | FAIL | INFO |
| ReplicaSet exists | FAIL | INFO only if directly managed |
| Deployment-owned ReplicaSet | Direct RS warning | Suppress direct-management warning |
| Image not digest-pinned | FAIL | WARN |
| `readOnlyRootFilesystem` missing | Always FAIL | WARN/hardening finding |

---

# 8. Suggested expected scanner summary for the bad fixtures

A useful scanner output model is:

```text
StatefulSet: insecure-stateful-app
Kubernetes validity:     PASS
Pod Security Restricted: FAIL
Security findings:       CRITICAL/HIGH
Production hardening:    WARNINGS
Operational guidance:    INFO

DaemonSet: insecure-node-agent
Kubernetes validity:     PASS
Pod Security Restricted: FAIL
Security findings:       CRITICAL/HIGH
Contextual findings:     hostPath / hostNetwork / privileged access
Production hardening:    WARNINGS

Job: insecure-data-processing
Kubernetes validity:     PASS
Pod Security Restricted: FAIL
Security findings:       CRITICAL/HIGH
Production hardening:    WARNINGS
Probe findings:          NONE

ReplicaSet: insecure-web
Kubernetes validity:     PASS
Pod Security Restricted: FAIL
Security findings:       CRITICAL/HIGH
Production hardening:    WARNINGS
Operational guidance:    INFO — direct ReplicaSet management

CronJob: insecure-daily-report
Kubernetes validity:     PASS
Pod Security Restricted: FAIL
Security findings:       CRITICAL/HIGH
Production hardening:    WARNINGS
Operational guidance:    INFO
Probe findings:          NONE
```

---

# 9. Recommended test strategy

For each scanner rule, maintain at least these fixtures:

```text
PASS
FAIL
EXCEPTION
```

For contextual rules, use:

```text
PASS
WARN
HIGH-RISK
LEGITIMATE-EXCEPTION
```

Example:

```text
K8S-SEC-HOSTPATH-001

PASS:
  No hostPath.

WARN:
  DaemonSet mounts /var/log read-only.

HIGH:
  Workload mounts /etc.

CRITICAL:
  Workload mounts /.

CRITICAL:
  Workload mounts container runtime socket.

EXCEPTION:
  Approved node monitoring DaemonSet with documented required host path.
```

This is substantially better than testing only:

```text
hostPath exists = bad
```

---

# 10. Recommended rule metadata

Each rule should carry enough metadata for the engine to make context-aware decisions.

```yaml
id: K8S-SEC-001
name: Privileged container
category: security
severity: critical

applies_to:
  - StatefulSet
  - DaemonSet
  - Job
  - ReplicaSet
  - CronJob

paths:
  - spec.template.spec.containers[*].securityContext.privileged
  - spec.jobTemplate.spec.template.spec.containers[*].securityContext.privileged

expected:
  value: false

pod_security_standard:
  restricted: prohibited

exceptions:
  daemonset:
    allowed_with_review: true

message: >
  Container is running in privileged mode and receives extensive
  access to host resources.

remediation: >
  Set securityContext.privileged to false unless the workload
  has a documented and approved requirement for privileged access.
```

This metadata allows the same rule to handle different workload object structures.

---

# 11. Path normalization recommendation

Your scanner should normalize the Pod template location.

For:

```text
StatefulSet
DaemonSet
ReplicaSet
Job
```

the Pod spec generally appears under:

```text
spec.template.spec
```

For:

```text
CronJob
```

it appears under:

```text
spec.jobTemplate.spec.template.spec
```

Internally, normalize these to something like:

```text
podSpec
```

Then rules can operate on:

```text
podSpec.containers[]
podSpec.securityContext
podSpec.hostNetwork
podSpec.hostPID
podSpec.volumes[]
```

rather than implementing every security rule five times.

---

# 12. Scanner finding hierarchy

Recommended output hierarchy:

```text
1. Kubernetes Validity
2. Pod Security Standards
3. Security Risks
4. Production Hardening
5. Operational / Business Guidance
```

Example:

```text
[CRITICAL] K8S-SEC-001
Privileged container

Object:
  DaemonSet/monitoring/insecure-node-agent

Path:
  spec.template.spec.containers[0].securityContext.privileged

Value:
  true

Impact:
  A privileged container receives broad access to host resources
  and significantly weakens container isolation.

Recommendation:
  Set privileged: false unless this node-level workload has an
  explicitly approved requirement.

Context:
  DaemonSets sometimes require elevated host access. This finding
  should remain visible but can support an approved exception.
```

---

# 13. Important distinction: invalid vs insecure

Your test suite should deliberately include both.

## Valid Kubernetes + insecure

Example:

```yaml
securityContext:
  privileged: true
```

This may be accepted by the Kubernetes API depending on admission policy, but it is insecure.

Scanner result:

```text
Kubernetes validity: PASS
Security: FAIL
```

## Invalid Kubernetes

Example Job:

```yaml
restartPolicy: Always
```

Scanner result:

```text
Kubernetes validity: FAIL
```

These are different categories and should not be combined.

---

# 14. Important distinction: insecure vs hardening recommendation

Example:

```yaml
securityContext:
  privileged: true
```

should be high severity.

But:

```yaml
securityContext:
  readOnlyRootFilesystem: false
```

is better represented as hardening guidance in a general-purpose scanner.

Similarly:

```text
CPU limit missing
```

should normally not have the same severity as:

```text
SYS_ADMIN capability added
```

Otherwise the scanner's results become noisy and users start ignoring findings.

---

# 15. Recommended negative fixture expectations

| Workload | Kubernetes validity | Restricted PSS | Security | Hardening | Context handling |
|---|---|---|---|---|---|
| StatefulSet bad fixture | PASS | FAIL | CRITICAL/HIGH | WARN | StatefulSet-specific |
| DaemonSet bad fixture | PASS | FAIL | CRITICAL/HIGH | WARN | Strong contextual handling |
| Job bad fixture | PASS | FAIL | CRITICAL/HIGH | WARN | Ignore missing probes |
| ReplicaSet bad fixture | PASS | FAIL | CRITICAL/HIGH | WARN | Direct-management INFO |
| CronJob bad fixture | PASS | FAIL | CRITICAL/HIGH | WARN | Concurrency is contextual |
| Invalid Job fixture | FAIL | N/A/secondary | N/A/secondary | N/A | Schema/API validation first |

---

# 16. Core principle

The scanner should not ask only:

```text
"Is this setting present?"
```

It should ask:

```text
1. Is the manifest valid Kubernetes?
2. Does the setting violate a defined security standard?
3. Is it a production hardening recommendation?
4. Is the setting legitimate for this workload type?
5. Does the surrounding configuration increase or reduce the risk?
6. Is an exception reasonable and auditable?
```

This is the key to reducing false positives while still identifying genuinely dangerous Kubernetes configurations.

---

# 17. Purpose of this file

This document is an intentionally insecure companion to the secure baseline test-case file.

Use the two together:

```text
secure fixtures
    ↓
expected PASS / INFO

insecure fixtures
    ↓
expected WARN / HIGH / CRITICAL

invalid fixtures
    ↓
expected Kubernetes validation FAIL

exception fixtures
    ↓
expected contextual warning or suppression
```

The combination gives the scanner a much stronger regression-test suite than simply checking whether a YAML field exists.
