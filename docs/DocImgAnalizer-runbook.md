# DocImgAnalizer — Runbook

## Production Deployment — Which Workflow To Run

**A plain `git push` never deploys anything.** Every deploy workflow in this repo
gates its actual deploy jobs on `github.event_name == 'workflow_dispatch'` — pushing
a branch only runs the `Validate` job (lint/test/build check). You must manually
trigger the workflow and choose an environment. `dev` was decommissioned 2026-07-17
to cut cost, so **`prod` is the only meaningful environment choice** — the `dev`
input still exists in the workflow but there's no dev infrastructure left for it to
target.

### The two production workflows and what each actually deploys

| ------------------------ | ------------------------------------------------------------------------------------------------------------------------------------------ |
| Workflow (GitHub name)   | What it deploys                                                                                                                              |
| ------------------------ | ------------------------------------------------------------------------------------------------------------------------------------------ |
| `deploy.yml` ("Deploy")  | `terraform/phase1` (API Gateway, v1 Lambda, S3 frontend bucket, CloudFront distribution) + the v1 (anonymous) Lambda from `backend/app/` + builds/syncs the frontend to S3 + invalidates CloudFront |
| `phase2-deploy.yml` ("Phase 2 Deploy") | `terraform/phase2` (Cognito, DynamoDB v2, CVE-report/SBOM S3 buckets, ECS scanner infra) + the v2 (authenticated) Lambda from `backend/v2/` + rebuilds the ECS Trivy+Syft scanner image + **also** builds/syncs the frontend to S3 + invalidates CloudFront |
| ------------------------ | ------------------------------------------------------------------------------------------------------------------------------------------ |

**Key fact: there is only one frontend.** One S3 bucket, one CloudFront
distribution, both owned by `terraform/phase1`. `phase2-deploy.yml`'s frontend step
literally reads `terraform/phase1`'s Terraform outputs (`frontend_bucket`,
`cloudfront_distribution_id`) to know where to push — it doesn't have its own
frontend infrastructure. Both workflows redundantly deploy to the same place.

### Deciding which one(s) to run

- **Change touches only `frontend/`** (no backend/terraform changes): run **either
  one** — both end in an identical frontend sync + CloudFront invalidation.
  `deploy.yml` is the simpler/faster pick since it doesn't also rebuild the ECS
  scanner image.
- **Change touches `backend/app/`** (v1, anonymous tier): run `deploy.yml`.
- **Change touches `backend/v2/`, `backend/scanner/`, or `terraform/phase2/`**: run
  `phase2-deploy.yml`.
- **Change touches both v1 and v2** (e.g. a new endpoint added to every tier, like
  the Kubernetes manifest analyzer): run **both** — each pipeline's backend-deploy
  step is independently needed, and the redundant double frontend-sync is harmless.
- **Change touches `terraform/phase1`**: run `deploy.yml` (it's the only workflow
  that applies that stack).
- v3 (`backend/v3/`, `terraform/phase3/`) has its own separate `phase3-deploy.yml`,
  not covered by either of the two above.

### Commands

```bash
# Push your branch first (workflow_dispatch runs against whatever ref you give it,
# so make sure your commits are actually on origin before triggering):
git push origin <branch>

# Trigger a deploy — --ref can be any branch, not just develop/main:
gh workflow run deploy.yml --ref <branch> -f environment=prod
gh workflow run phase2-deploy.yml --ref <branch> -f environment=prod

# Watch it run (prints each job/step live, exits non-zero on failure):
gh run list --workflow=deploy.yml --limit 1        # get the run ID
gh run watch <run-id> --exit-status

# Verify after it finishes — hit the actual endpoint/page, don't just trust "green":
curl https://img.craftingnewtech.com/api/v1/health
curl -X POST https://img.craftingnewtech.com/api/v1/analyze/kubernetes -H "Content-Type: application/json" -d '{"content": "..."}'
```

## Local Development — Full App Round-Trip (Backend + Frontend, No AWS)

Dev was decommissioned 2026-07-17 to cut cost — there is no shared dev
environment to point the frontend at. A full local round-trip (submit a
scan through the actual UI and see a real result) needs the backend's AWS
calls stubbed out, since `DYNAMODB_TABLE_NAME=test-table` /
`REPORTS_BUCKET_NAME=test-bucket` are not real resources.

This works for any of the sync `/analyze/*` endpoints (Dockerfile,
Kubernetes manifest) — none of them need a live AWS backend to *compute* a
result, only the DB/S3 write on the way out needs stubbing. The async image
scan (`/analyze/image`) additionally needs `ecs_launcher.launch_scan`
stubbed, since it always submits a real ECS task.

### Prerequisites

Same as the project-wide local dev setup: Python 3.12 venv at
`backend/.venv` with `requirements-dev.txt` installed, and
`frontend/node_modules` via `npm ci`.

### Steps

**1. Terminal 1 — start the backend** with `dynamodb.put_scan` /
`_store_report` stubbed to no-ops so it never touches real AWS, and CORS
opened for the local frontend origin:

```bash
cd backend
DYNAMODB_TABLE_NAME=test-table REPORTS_BUCKET_NAME=test-bucket ENVIRONMENT=test \
ALLOWED_ORIGIN=http://localhost:5183 \
.venv/bin/python -c "
import app.routers.analyze as r
r.dynamodb.put_scan = lambda *a, **k: None
r._store_report = lambda *a, **k: None
from app.main import app
import uvicorn
uvicorn.run(app, host='127.0.0.1', port=8811)
"
```

Confirm it's up: `curl http://127.0.0.1:8811/api/v1/health`

**2. Terminal 2 — start the frontend**, pointed at that backend:

```bash
cd frontend
VITE_API_BASE_URL=http://127.0.0.1:8811 npm run dev -- --port 5183
```

**3. Open the browser** at `http://localhost:5183/` and exercise the flow —
e.g. for the Kubernetes manifest analyzer, click the **Kubernetes Manifest**
tab, paste a manifest, and submit. Try both a manifest with known issues
(unpinned image, `privileged: true`, `hostNetwork: true`) and a hardened one
(pinned image, `runAsNonRoot: true`, resource limits, probes,
`capabilities.drop: ["ALL"]`) to see both a low-score and a 100/100 result.

**4. Stop both servers when done:**

```bash
pkill -f "uvicorn"; pkill -f "vite --port 5183"
```

### Restarting the backend after a code change

The backend above is started with plain `uvicorn.run(...)` — **no `--reload`** — so it
loads `app/` into memory once and will not pick up edits to Python files (e.g. a rule
change in `k8s_manifest_analyzer.py`) until it's restarted. The frontend dev server
(Vite) has hot-reload built in and does not need restarting for frontend-only changes.

**1. Stop the running backend:**

```bash
pkill -f "uvicorn.run(app"
# or, more broadly: lsof -ti :8811 | xargs kill
```

**2. Start it again** — same command as step 1 above:

```bash
cd backend
DYNAMODB_TABLE_NAME=test-table REPORTS_BUCKET_NAME=test-bucket ENVIRONMENT=test \
ALLOWED_ORIGIN=http://localhost:5183 \
.venv/bin/python -c "
import app.routers.analyze as r
r.dynamodb.put_scan = lambda *a, **k: None
r._store_report = lambda *a, **k: None
from app.main import app
import uvicorn
uvicorn.run(app, host='127.0.0.1', port=8811)
"
```

**3. Confirm it's back up:** `curl http://127.0.0.1:8811/api/v1/health`, then refresh
the browser tab and re-test — no need to restart the frontend.

### Gotchas

- **`ALLOWED_ORIGIN` must match the frontend's origin exactly**, or the
  browser blocks every request with a CORS error (`No 'Access-Control-Allow-Origin'
  header`). This is the app's real CORS middleware (`backend/app/main.py`),
  not a test-only shim — it defaults to the production frontend origin
  (`https://imgapp.craftingnewtech.com`) when the env var isn't set.
- **Vite binds to `::1` (IPv6 localhost) by default**, not `127.0.0.1`. Use
  `http://localhost:5183`, not `http://127.0.0.1:5183`, when checking the
  frontend is up.
- **Don't skip the stub step and point at real AWS** unless you deliberately
  want to write test scan data into real DynamoDB/S3 — `test-table`/
  `test-bucket` will just 404/`ResourceNotFoundException` if your local AWS
  credentials are valid but those resource names don't exist in the account.
