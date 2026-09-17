# DocImgAnalizer — Kubernetes Manifest Analyzer: Pending Improvements (V1)

## Purpose

Tracking doc for the gap-analysis run against two external scanner test-case reference
files (`kubernetes_workload_misconfiguration_scanner_bad_test_cases.md` and
`kubernetes_workload_misconfiguration_scanner_complete_test_cases.md`, both in `docs/`).
Items 1-3 are already implemented; the rest are logged here for prioritization in a
later session rather than being built speculatively. See
`docs/DocImgAnalizer-K8sManifestExamples-V1.md` for the current, verified rule set and
worked examples.

## Already implemented

| - | ------------------------------------------- | ------- | ------ |
| # | Item                                        | Rule(s) | Status |
| - | ------------------------------------------- | ------- | ------ |
| 1 | Hardcoded secret in `env[].value`           | K011    | Done   |
| 2 | `automountServiceAccountToken` not disabled | K012    | Done   |
| 3 | Missing/unsafe seccomp profile              | K013    | Done   |
| - | ------------------------------------------- | ------- | ------ |

## Pending

| -- | ------------------------------------------------------------------------------------------------------------ | ---------------------------------------------- | -------------------------------------- | ----------- |
| #  | Item                                                                                                          | Affects                                        | Category                               | Status      |
| -- | ------------------------------------------------------------------------------------------------------------ | ---------------------------------------------- | -------------------------------------- | ----------- |
| 4  | Path-based hostPath severity (`/`, socket = CRITICAL; `/etc`/`/proc`/`/sys` = HIGH; `/var/log`-style = WARN) | K007                                           | Refine existing rule                   | Not started |
| 5  | Dangerous-capability-specific severity (SYS_ADMIN/NET_ADMIN/SYS_PTRACE higher than generic add)               | K008                                           | Refine existing rule                   | Not started |
| 6  | Lighter WARN tier for tag-pinned-but-not-digest-pinned images                                                 | K001                                           | Refine existing rule                   | Not started |
| 7  | Split resource check into memory request/limit + CPU request/limit, each its own severity                    | K005                                           | Refine existing rule                   | Not started |
| 8  | Job lifecycle fields: excessive backoffLimit, missing activeDeadlineSeconds/ttlSecondsAfterFinished           | Job                                            | New field outside PodSpec              | Not started |
| 9  | CronJob lifecycle fields: missing startingDeadlineSeconds/timeZone, excessive history limits                  | CronJob                                        | New field outside PodSpec              | Not started |
| 10 | StatefulSet volumeClaimTemplates access mode: ReadWriteOnce vs ReadWriteOncePod                                | StatefulSet                                    | New field outside PodSpec              | Not started |
| 11 | restartPolicy: Always on Job/CronJob (API-rejected, not currently validated at all)                           | Job, CronJob                                   | Kubernetes schema validity (new layer) | Not started |
| 12 | Selector/template label mismatch (API-rejected, not currently validated)                                      | Deployment, StatefulSet, DaemonSet, ReplicaSet | Kubernetes schema validity (new layer) | Not started |
| -- | ------------------------------------------------------------------------------------------------------------ | ---------------------------------------------- | -------------------------------------- | ----------- |

## Flagged as likely out of scope

Not proposing these unless priorities change — logged so they aren't silently dropped.

| -- | -------------------------------------------- | ------------------------------------------------------------------------------------------------------------------------------------------- |
| #  | Item                                          | Why flagged out of scope                                                                                                                     |
| -- | -------------------------------------------- | ------------------------------------------------------------------------------------------------------------------------------------------- |
| 13 | NetworkPolicy existence check                 | A separate Kubernetes object entirely — would need cross-object detection across the submitted manifest bundle, not a single-PodSpec check.  |
| 14 | ReplicaSet ownerReferences-based suppression  | Only relevant if a "direct ReplicaSet management" finding is added first — we don't have one today, so there's nothing to suppress.          |
| -- | -------------------------------------------- | ------------------------------------------------------------------------------------------------------------------------------------------- |

## Notes for whoever picks this up next

- Items 4-7 are the highest-value/lowest-effort next batch — they refine existing rules
  (K001/K005/K007/K008) rather than adding new PodSpec parsing paths, so they follow the
  same shape as the K011-K013 work already done.
- Items 8-10 require parsing fields the analyzer doesn't touch today (`backoffLimit`,
  `activeDeadlineSeconds`, `ttlSecondsAfterFinished` on Job/CronJob;
  `volumeClaimTemplates` on StatefulSet) — first time reading outside `PodSpec`.
- Items 11-12 are a structurally different kind of check ("is this even valid
  Kubernetes" vs. "is this configured securely/well") — worth deciding whether they
  belong in this analyzer at all, or as a separate pre-check, before implementing.
- Whichever items get picked up, follow the same verify-then-document discipline used
  throughout this feature: run real manifests through the analyzer to get exact
  scores/findings before writing them into a doc, don't hand-compute.
