# DocImgAnalizer — Lambda MicroVMs Analysis (Phase 2 Scanner)

## Lambda MicroVMs vs. ECS Fargate for the async scanner (evaluated 2026-07-13)

AWS GA'd [Lambda MicroVMs](https://aws.amazon.com/blogs/compute/announcing-lambda-microvms-serverless-compute-environments-with-vm-level-isolation-and-near-instant-startup/) in June 2026 — Firecracker-based, ARM64-only sandboxes built with an image-then-launch model, with suspend/resume to preserve state across a session. AWS names vulnerability scanning as a target use case, so the Trivy/Syft scanner (`backend/scanner/`) was evaluated as a migration candidate off ECS Fargate.

**Decision: keep ECS Fargate.** MicroVMs' headline benefit — VM-level isolation instead of a shared-kernel container — is not a net-new benefit here: Fargate already runs every task in its own Firecracker microVM. The feature MicroVMs are actually built around (fast snapshot-resume across a long-lived, stateful session) doesn't apply to a one-shot batch job that runs Trivy+Syft and exits.

| ----------------------------- | --------------------------------------------- | --------------------------------------------- |
| Dimension                     | ECS Fargate (current)                         | Lambda MicroVMs (ARM64)                       |
| ----------------------------- | --------------------------------------------- | --------------------------------------------- |
| Isolation                     | Firecracker VM per task (already)             | Firecracker VM per instance (same)            |
| Compute rate (0.5 vCPU / 1GB) | $0.04048/vCPU-hr + $0.004445/GB-hr            | $0.0000276944/vCPU-sec + $0.0000036667/GB-sec |
| Fixed monthly floor           | $0 (scales to zero between scans)             | ~$0.08-0.16/mo snapshot storage (dev+prod)    |
| Per-launch fees               | None beyond task start                        | $0.00155/GB resume + $0.0038/GB suspend       |
| EventBridge Pipes target      | Native (current wiring)                       | Not supported yet - needs orchestrator Lambda |
| Code model                    | One-shot CLI, exits on completion             | Long-lived HTTPS server (scan.py rewrite)     |
| CPU architecture              | x86 (current image as-is)                     | ARM64 only (image rebuild required)           |
| Est. cost at current volume   | <$0.01/mo (~10-15s/scan, CloudWatch-verified) | current cost + $0.08-0.16/mo fixed floor      |
| ----------------------------- | --------------------------------------------- | --------------------------------------------- |

Migrating would add a new fixed monthly cost floor, an ARM64 rebuild, a rewrite of `scan.py` from a one-shot CLI into a long-lived HTTP server, and a new orchestrator Lambda (EventBridge Pipes has no native MicroVM target yet) — for a workload that is already effectively free at this volume. Revisit only if the product adds a use case MicroVMs are actually designed for: long-lived, stateful, multi-tenant sandboxes (e.g. letting a user submit arbitrary code/scripts for interactive, repeated execution) rather than a single batch scan-and-exit.

**Operational / maintenance perspective:** beyond cost, Fargate is also the lower-overhead choice today because the tooling around MicroVMs hasn't caught up to a 4-week-old GA service.

| --------------------- | ---------------------------------------------------- | ----------------------------------------- |
| Dimension             | ECS Fargate (current)                                | Lambda MicroVMs (ARM64)                   |
| --------------------- | ---------------------------------------------------- | ----------------------------------------- |
| Deployment mechanism  | Build -> ECR -> task def revision -> Pipe update [1] | Build -> snapshot image -> update ARN [2] |
| IaC tooling           | Native Terraform - mature                            | No Terraform support yet [3]              |
| Runtime/OS patching   | AWS patches host; we patch base image                | Same, plus manual snapshot cleanup [4]    |
| Rollback              | One `terraform apply` to prior revision              | No documented rollback primitive [5]      |
| Scaling / concurrency | Native Pipes batching, documented quotas             | Untested concurrency limits [6]           |
| Observability         | CloudWatch Logs + Container Insights wired           | Same CloudWatch model, new wiring needed  |
| Local dev parity      | `docker run` matches prod exactly                    | No local emulator [7]                     |
| Service maturity      | GA since 2017                                        | GA 4 weeks old (2026-06-22)               |
| --------------------- | ---------------------------------------------------- | ----------------------------------------- |

**Details:**

1. Build -> push ECR -> new task def revision -> EventBridge Pipe target updated — fully automated in `phase2-deploy.yml`.
2. Build -> `create-microvm-image` (new snapshot publish step) -> update the image ARN reference used by the launcher.
3. No Terraform resource yet (open [hashicorp/terraform-provider-aws#48526](https://github.com/hashicorp/terraform-provider-aws/issues/48526)); only CloudFormation/CDK manage the static image resource today — this project is 100% Terraform (see `terraform-gotchas.md`), so adopting it now means either mixing in CloudFormation or wrapping the AWS SDK in a custom Lambda/`local-exec`.
4. AWS patches the Firecracker host; we still own rebuilding the snapshot for base image CVEs, plus running `delete-microvm-image` ourselves so stale snapshots don't accrue storage cost.
5. No documented rollback primitive — revert to the prior image ARN and re-run create/launch manually via API/SDK.
6. Concurrency limits for a 4-week-old GA service are untested at our scale — an added unknown.
7. No documented local emulator — testing requires the AWS control plane (create/launch cycle) in a dev account.

The standout gap is IaC tooling maturity (see [3] above) — the per-run MicroVM instances are API/SDK-driven regardless of IaC tool, but the lack of a Terraform resource for even the static image cuts against the "everything in Terraform" pattern used everywhere else in this repo.

---

*DocImgAnalizer Phase 2 — craftingnewtech.com*
