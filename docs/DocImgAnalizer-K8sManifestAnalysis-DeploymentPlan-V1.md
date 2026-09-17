# DocImgAnalizer — Kubernetes Manifest Analysis — Deployment Plan (V1)

> **Historical planning doc — rule count is stale.** This plan was written before
> implementation and describes the original 10-rule design (K001-K010). The shipped
> analyzer has since grown to 13 rules (K011-K013 added after a gap review against an
> external scanner test-case spec) and picked up several kind-aware severity
> adjustments. For the current, continuously-verified rule set and examples, see
> `docs/DocImgAnalizer-K8sManifestExamples-V1.md` instead — this doc is kept as-is for
> historical record of the original feasibility/design decision, not as a living spec.

## Is it possible?

**Yes, with no architectural blockers.** The codebase already has a proven template for
exactly this shape of feature — the Dockerfile analyzer — and Kubernetes manifest analysis
slots into the same pattern without requiring new AWS infrastructure, new IAM permissions,
or a new Terraform module. It is a pure application-code addition (Python rule engine +
FastAPI routes + a React tab), deployed through the existing pipeline.

## What "Kubernetes Manifest Analysis" means here

A user pastes raw Kubernetes YAML (`Deployment`, `Pod`, `StatefulSet`, `DaemonSet`, `Job`,
`CronJob`, `ReplicaSet`) into a new third tab next to "Dockerfile Analysis" and "Image
Scan", and gets back a 0-100 security score plus a findings list — the same result shape
already used for Dockerfile scans today.

## Why this is low-risk to build

| ------------------------- | -------------------------------------------------------------------- |
| Dimension                 | Assessment                                                            |
| ------------------------- | -------------------------------------------------------------------- |
| New AWS resources         | None — no Terraform changes, no new Lambda, no new IAM policy         |
| New dependencies          | One: `PyYAML` (pure static-analysis parsing, no network/exec calls)   |
| Existing pattern to reuse | `backend/app/services/dockerfile_analyzer.py` (rule engine shape)     |
| API surface change        | 3 new `POST /analyze/kubernetes` routes (v1, v2, v3) — additive only  |
| Frontend change           | 1 new tab reusing the existing findings-rendering UI, no new page     |
| DB/schema change          | None — `scan_type` is already a free-form string field in DynamoDB    |
| Cost impact               | ~$0/mo — same Lambda, same DynamoDB table, no new billable resource   |
| ------------------------- | -------------------------------------------------------------------- |

## Technical approach (condensed)

1. **Rule engine** — new file `backend/app/services/k8s_manifest_analyzer.py`, parsing with
   `yaml.safe_load_all` (never `yaml.load` — untrusted input) and walking each document's pod
   spec (containers + initContainers). Ten rules, `K001`-`K010`, scored the same way the
   Dockerfile engine's `R001`-`R011` are (severity-weighted deductions from 100):

   | ---- | -------- | --------- | ---------------------------------------------------------- |
   | Rule | Severity | Deduction | Check                                                       |
   | ---- | -------- | --------- | ---------------------------------------------------------- |
   | K001 | error    | -20       | Container image unpinned (`:latest` or no tag)              |
   | K002 | error    | -30       | `securityContext.privileged: true`                          |
   | K003 | error    | -25       | No `runAsNonRoot: true` at pod or container level            |
   | K004 | warning  | -15       | `allowPrivilegeEscalation` not explicitly `false`            |
   | K005 | warning  | -10       | Missing `resources.requests`/`resources.limits` (cpu+memory) |
   | K006 | error    | -25       | `hostNetwork` / `hostPID` / `hostIPC: true`                  |
   | K007 | warning  | -15       | `hostPath` volume defined                                    |
   | K008 | warning  | -10       | Capabilities not dropped (`drop: [ALL]` missing) or added    |
   | K009 | info     | -5        | No liveness/readiness probes                                 |
   | K010 | info     | -10       | `readOnlyRootFilesystem` not `true`                           |
   | ---- | -------- | --------- | ---------------------------------------------------------- |

   No whole-file auto-fix output (the Dockerfile engine's `fixed_dockerfile` rewrite is a
   large, format-preserving text-rewrite pass — out of scope for a first version). Each
   finding still carries a per-rule `fix` suggestion string, same as the Dockerfile rules.

2. **Schemas** — add `kubernetes` to the `ScanType` enum in all three tiers
   (`backend/app/models/schemas.py`, `backend/v2/models/schemas.py`,
   `backend/v3/models/schemas.py`) and a `KubernetesAnalyzeRequest(content: str)` model.
   The existing `DockerfileAnalyzeResponse` shape is reused as-is (its `fixed_dockerfile`
   field is simply empty for a kubernetes scan) — no new response type needed.

3. **Routers** — one new `POST /analyze/kubernetes` endpoint per tier
   (`backend/app/routers/analyze.py`, `backend/v2/routers/analyze.py`,
   `backend/v3/routers/analyze.py`), each a direct structural mirror of that tier's existing
   `analyze_dockerfile` handler (same auth dependency, same DynamoDB `put_scan` call, same
   error handling).

4. **Frontend** — a third `HomePage.tsx` tab, two new `api/client.ts` functions
   (`analyzeKubernetes`, `analyzeKubernetesV2`), and a small generalization of the
   `isDockerfile` check in `ResultsPage.tsx` / `DeepResultsPage.tsx` to
   `isFindingsBased = scan_type === 'dockerfile' || scan_type === 'kubernetes'` — both pages
   already render score + findings generically, so no new result component is needed.

5. **Tests** — `backend/tests/test_k8s_manifest_analyzer.py` (one test per rule, mirroring
   `test_dockerfile_analyzer.py`), plus one router-level happy-path test added to each of
   `test_routers.py` / `test_v2_routers.py` / `test_v3_routers.py`. Required to hold the
   existing `--cov-fail-under=80` gate in `make check`.

## Dependency addition

| ------------------------------- | ------------- | ------------------------------------------------ |
| Package                         | Version pin   | Where                                             |
| ------------------------------- | ------------- | -------------------------------------------------- |
| `PyYAML`                        | `6.0.2`       | `backend/requirements.txt` (shared by all 3 tiers) |
| `types-PyYAML`                  | `6.0.12.20250326` | `backend/requirements-dev.txt` (mypy stub)     |
| ------------------------------- | ------------- | -------------------------------------------------- |

PyYAML ships prebuilt `manylinux` wheels for Python 3.12, so the existing Lambda build step
(`pip install --platform manylinux2014_x86_64 --python-version 3.12 --only-binary=:all:`)
picks it up with no build-step changes. `pip-audit` (part of `make check`) will independently
verify no known CVEs on the pinned version before merge.

## Deployment mechanics — no new infrastructure

Because this ships entirely inside the existing Lambda packages (v1/v2/v3 all bundle
`backend/app/`, per the existing comment in `backend/v2/routers/analyze.py`), deployment is
just the normal code pipeline — no Terraform apply, no manual AWS console step, no new IAM
grant to review.

**Rollout steps:**

1. Branch off `phase2` (the current live/clean branch per project memory — `main`'s
   `terraform/phase2` is stale and must not be used as a base for anything terraform-adjacent,
   though this change itself touches no Terraform).
2. Implement per the file list above; run `make check` locally (ruff, mypy x3, pytest with
   coverage, pip-audit, trivy IaC, npm lint/build/audit) before any push — this change should
   not add any new IaC findings since no `terraform/` files are touched.
3. Open a PR — `pr.yml` runs the same gate in CI (per-job `dorny/paths-filter` gating, unified
   `pr-ready` check).
4. Merge to `develop` → auto-deploys (per existing pipeline convention). Prod is the only live
   environment (dev was decommissioned 2026-07-17), so verify on prod's actual domain.
5. Smoke-test: `make smoke-test` (hits live API endpoints) — extend
   `scripts/smoke-test.sh` with a `POST /api/v1/analyze/kubernetes` call if the script
   enumerates known routes explicitly.

**Rollback:** standard — revert the merge commit and redeploy. No data migration, no stateful
resource created, so rollback has no cleanup step beyond the code revert.

## Cost impact

**+$0.00/mo.** No new AWS resource is created. The additional Lambda package size from
`PyYAML` (~2-3 MB) is negligible against the existing package size and Lambda's 250 MB
unzipped limit. No new DynamoDB attribute type, no new S3 prefix pattern beyond the existing
`reports/{scan_id}.json` convention already used for Dockerfile/image scans.

## Example manifest — rule mapping

The annotated manifest below is the intended `BAD_MANIFEST` test fixture for
`backend/tests/test_k8s_manifest_analyzer.py` — every rule K001-K010 fires exactly once
against it. Comments show which rule flags which line; the numbered list below the YAML
gives the same mapping as a table for quick scanning.

```yaml
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
      hostNetwork: true                        # (6) K006 - hostNetwork: true
      hostPID: true                             # (6) K006 - hostPID: true (same rule, pod-level check)
      containers:
        - name: web
          image: nginx                          # (1) K001 - no tag -> unpinned image
          securityContext:
            privileged: true                    # (2) K002 - privileged container
            allowPrivilegeEscalation: true       # (4) K004 - not explicitly false
            capabilities:
              add: ["SYS_ADMIN"]                 # (8) K008 - capability added, no "drop: [ALL]"
            readOnlyRootFilesystem: false        # (10) K010 - root filesystem writable
          # no "resources:" block anywhere here  # (5) K005 - missing requests/limits
          # no "runAsNonRoot: true" at pod        (3) K003 - container may run as root
          # or container securityContext level
          volumeMounts:
            - name: host-data
              mountPath: /data
          # no livenessProbe / readinessProbe    # (9) K009 - no health probes
      volumes:
        - name: host-data
          hostPath:                              # (7) K007 - hostPath volume
            path: /var/lib/docker
```

| ---- | -------------------------------------------- | ------------------------------------------------------- |
| Rule | Manifest location                             | What trips it                                            |
| ---- | -------------------------------------------- | ------------------------------------------------------- |
| K001 | `spec.template.spec.containers[0].image`      | `nginx` has no `:tag` — unpinned image                   |
| K002 | `containers[0].securityContext.privileged`    | `true`                                                    |
| K003 | pod spec + container spec (absence check)     | `runAsNonRoot` not set anywhere in the pod                |
| K004 | `containers[0].securityContext.allowPrivilegeEscalation` | `true`, not explicitly `false`                |
| K005 | `containers[0].resources` (absence check)     | No `requests`/`limits` block at all                       |
| K006 | `spec.template.spec.hostNetwork` / `hostPID`  | Both `true`                                                |
| K007 | `spec.template.spec.volumes[0].hostPath`      | Mounts `/var/lib/docker` from the host node                |
| K008 | `containers[0].securityContext.capabilities`  | `add: [SYS_ADMIN]` with no `drop: [ALL]`                    |
| K009 | `containers[0]` (absence check)               | No `livenessProbe`/`readinessProbe` defined                |
| K010 | `containers[0].securityContext.readOnlyRootFilesystem` | `false`                                          |
| ---- | -------------------------------------------- | ------------------------------------------------------- |

**For contrast, the hardened version of the same manifest** (this is the intended
`GOOD_MANIFEST` fixture — score ≥ 80, zero `error`-severity findings):

```yaml
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
      securityContext:
        runAsNonRoot: true
        runAsUser: 1000
      containers:
        - name: web
          image: nginx:1.29-alpine              # K001 fixed - pinned tag
          securityContext:
            privileged: false                    # K002 fixed
            allowPrivilegeEscalation: false       # K004 fixed
            readOnlyRootFilesystem: true          # K010 fixed
            capabilities:
              drop: ["ALL"]                       # K008 fixed
          resources:                              # K005 fixed
            requests:
              cpu: 100m
              memory: 128Mi
            limits:
              cpu: 250m
              memory: 256Mi
          livenessProbe:                          # K009 fixed
            httpGet:
              path: /healthz
              port: 8080
            initialDelaySeconds: 5
          readinessProbe:                         # K009 fixed
            httpGet:
              path: /ready
              port: 8080
      volumes: []                                 # K007 fixed - no hostPath volume
```

## Verification plan (post-implementation, before merge)

- `make check` passes clean (full local gate).
- Manually submit the bad manifest above through the new tab, both signed-out (`v1`) and
  signed-in (`v2`), confirm all 10 `K00x` findings appear and the score reflects the
  deductions (100 - (20+30+25+15+10+25+15+10+5+10) = 0, clamped at the floor).
- Submit the hardened manifest above and confirm a high score (>=80) with zero `error`
  findings — mirrors the existing `test_good_dockerfile_high_score` assertion style.
- Confirm scan history (`GET /api/v2/scans`) lists kubernetes scans correctly alongside
  dockerfile/image scans (this endpoint is scan-type-agnostic already, per
  `backend/v2/routers/scans.py` — no change expected there, just a check).

## Open questions for review

- **Auto-fix parity** — should a `fixed_manifest` output (mirroring `fixed_dockerfile`) be a
  fast-follow, or is per-finding `fix` text sufficient long-term? Recommend treating this as
  a separate, later enhancement rather than blocking V1 on it.
- **v3 UI wiring** — v3 currently has no frontend surface at all (billing/API-key tier, not
  yet wired into `HomePage.tsx` for any scan type). This plan adds the v3 endpoint for parity
  with the existing Dockerfile/image pattern, but it will be API-only until v3 gets a UI in a
  separate effort — confirm that's acceptable rather than a gap specific to this feature.
