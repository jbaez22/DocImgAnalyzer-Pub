# DocImgAnalizer — Technical Diagrams (Phase 1)

All diagrams are written in [Mermaid](https://mermaid.js.org/) and render natively
in GitHub, GitLab, Notion, and most modern markdown viewers.

---

## Diagram 1 — AWS Architecture

Shows every AWS service deployed in Phase 1, how they connect, and the security
controls applied at each layer.

```mermaid
graph TB
    %% ── External actors ──────────────────────────────────────────────────────
    User(["👤 User\n(Browser)"])
    GHA(["⚙️ GitHub Actions\n(CI/CD — OIDC)"])
    DockerHub(["🐳 Docker Hub\nPublic API"])

    %% ── DNS ──────────────────────────────────────────────────────────────────
    subgraph DNS ["Route 53"]
        R53_FE["imgapp.craftingnewtech.com\nA alias → CloudFront"]
        R53_API["img.craftingnewtech.com\nA alias → API Gateway"]
    end

    %% ── Frontend delivery ────────────────────────────────────────────────────
    subgraph Frontend ["Frontend — CloudFront + S3"]
        WAF["WAF WebACL\nManaged rules\nRate limit: 1000 req/5 min"]
        CF["CloudFront Distribution\nHTTPS only · TLS 1.2+\nOAC enforced · Price Class 100"]
        S3_FE["S3 Frontend Bucket\nReact + Vite SPA\nPublic access blocked\nVersioning enabled"]
    end

    %% ── API layer ────────────────────────────────────────────────────────────
    subgraph API ["API — API Gateway HTTP API v2"]
        APIGW["Custom Domain\nimg.craftingnewtech.com\nThrottle: burst 100 · rate 50 rps\nCORS: imgapp.craftingnewtech.com only"]
    end

    %% ── Compute ──────────────────────────────────────────────────────────────
    subgraph Compute ["Compute — Lambda"]
        LAMBDA["img-analyzer-prod-api\nPython 3.12 · FastAPI · Mangum\n512 MB · 30 s timeout"]
        subgraph Services ["Analysis Services"]
            DF_SVC["Dockerfile Analyzer\n7-rule custom engine\nPure Python — no external tools"]
            IMG_SVC["Image Analyzer\nDocker Hub REST API\nMetadata only — no image pull"]
        end
    end

    %% ── Persistence ──────────────────────────────────────────────────────────
    subgraph Persistence ["Persistence"]
        DDB["DynamoDB\nimg-analyzer-prod-scans\nOn-Demand · PITR enabled\nKMS encrypted · TTL 90 days"]
        S3_RPT["S3 Reports Bucket\nimg-analyzer-prod-reports\nFull JSON reports\nKMS encrypted"]
    end

    %% ── Security ─────────────────────────────────────────────────────────────
    subgraph Security ["Security"]
        KMS["KMS CMK\nAuto-rotate annually\nUsed by: DynamoDB · S3 · Lambda env vars"]
        ACM["ACM Certificate\nTLS for both domains\nus-east-1"]
    end

    %% ── Observability ────────────────────────────────────────────────────────
    subgraph Observability ["Observability"]
        CW_LOGS["CloudWatch Logs\nStructured JSON\n14-day retention"]
        CW_DASH["CloudWatch Dashboard\nLambda · API GW · DynamoDB metrics"]
        CW_ALARMS["CloudWatch Alarms\nErrors · Latency · Throttles · 5xx"]
        SNS["SNS Topic\nEmail alerts → you@example.com"]
    end

    %% ── Connections ──────────────────────────────────────────────────────────
    User -->|"HTTPS"| R53_FE
    User -->|"HTTPS"| R53_API
    R53_FE --> CF
    R53_API --> APIGW
    WAF -->|"Inspect"| CF
    CF -->|"OAC"| S3_FE
    APIGW -->|"Lambda proxy\npayload v2.0"| LAMBDA
    LAMBDA --> DF_SVC
    LAMBDA --> IMG_SVC
    IMG_SVC -->|"HTTPS GET"| DockerHub
    LAMBDA -->|"PutItem / GetItem"| DDB
    LAMBDA -->|"PutObject"| S3_RPT
    LAMBDA -->|"JSON logs"| CW_LOGS
    CW_LOGS --> CW_DASH
    CW_LOGS --> CW_ALARMS
    CW_ALARMS --> SNS
    KMS -.->|"Encrypt"| DDB
    KMS -.->|"Encrypt"| S3_RPT
    KMS -.->|"Encrypt env vars"| LAMBDA
    ACM -.->|"TLS cert"| CF
    ACM -.->|"TLS cert"| APIGW
    GHA -->|"UpdateFunctionCode\n(OIDC — no static keys)"| LAMBDA
    GHA -->|"S3 sync\nCloudFront invalidation"| S3_FE
```

---

## Diagram 2 — Data Flow

Shows the step-by-step flow of data through the system for each of the three
API operations: Dockerfile analysis, Image analysis, and Results retrieval.

```mermaid
sequenceDiagram
    actor User as User (Browser)
    participant FE as Frontend<br/>(CloudFront + S3)
    participant APIGW as API Gateway<br/>HTTP API v2
    participant Lambda as Lambda<br/>(FastAPI)
    participant DFSvc as Dockerfile<br/>Analyzer
    participant IMGSvc as Image<br/>Analyzer
    participant Hub as Docker Hub<br/>Public API
    participant DDB as DynamoDB
    participant S3 as S3 Reports

    Note over User,S3: ── Flow A: Dockerfile Analysis ──────────────────────────────

    User->>FE: Open imgapp.craftingnewtech.com
    FE-->>User: Serve React SPA (CloudFront cache)

    User->>FE: Paste Dockerfile content → click Analyze
    FE->>APIGW: POST /api/v1/analyze/dockerfile<br/>{ "content": "FROM ..." }
    APIGW->>Lambda: Proxy event (payload v2.0)

    Lambda->>Lambda: Validate request (Pydantic)
    Lambda->>DFSvc: analyze(content)

    DFSvc->>DFSvc: 1. Parse instructions<br/>(handles continuations, comments)
    DFSvc->>DFSvc: 2. Run rules R001–R007<br/>(regex + string matching)
    DFSvc->>DFSvc: 3. Calculate score (0–100)
    DFSvc->>DFSvc: 4. Generate fixed Dockerfile<br/>(3-pass transformation)
    DFSvc-->>Lambda: AnalysisResult<br/>(score, findings, fixed_dockerfile, metadata)

    Lambda->>S3: PutObject reports/<scan_id>.json
    S3-->>Lambda: OK

    Lambda->>DDB: PutItem (scan_id, score, findings, TTL)
    DDB-->>Lambda: OK

    Lambda-->>APIGW: AnalysisReport JSON
    APIGW-->>FE: 200 OK + AnalysisReport
    FE-->>User: Results page<br/>(score, findings + fixes, fixed Dockerfile)

    Note over User,S3: ── Flow B: Image Analysis ───────────────────────────────────

    User->>FE: Enter image name (e.g. nginx:1.25-alpine) → click Analyze
    FE->>APIGW: POST /api/v1/analyze/image<br/>{ "image": "nginx:1.25-alpine" }
    APIGW->>Lambda: Proxy event

    Lambda->>Lambda: Validate request (Pydantic)
    Lambda->>IMGSvc: analyze("nginx:1.25-alpine")

    IMGSvc->>IMGSvc: Parse image ref<br/>→ (library, nginx, 1.25-alpine)
    IMGSvc->>Hub: GET /v2/repositories/library/nginx/tags/1.25-alpine/
    Hub-->>IMGSvc: Tag metadata JSON

    IMGSvc->>IMGSvc: Extract digest, arch, OS,<br/>size, layer count

    alt Image not found
        Hub-->>IMGSvc: 404
        IMGSvc-->>Lambda: ValueError
        Lambda-->>APIGW: 404 Not Found
        APIGW-->>FE: { "detail": "Image not found" }
        FE-->>User: Error message
    else Upstream error
        Hub-->>IMGSvc: 5xx / timeout
        IMGSvc-->>Lambda: RuntimeError
        Lambda-->>APIGW: 502 Bad Gateway
    end

    IMGSvc-->>Lambda: ImageMetadata
    Lambda->>S3: PutObject reports/<scan_id>.json
    Lambda->>DDB: PutItem (scan_id, metadata, TTL)
    Lambda-->>APIGW: AnalysisReport JSON
    APIGW-->>FE: 200 OK + AnalysisReport
    FE-->>User: Results page<br/>(image metadata: digest, arch, OS, size)

    Note over User,S3: ── Flow C: Results Retrieval (direct URL / page refresh) ──

    User->>FE: Navigate to /results/<scan_id>
    FE->>APIGW: GET /api/v1/results/<scan_id>
    APIGW->>Lambda: Proxy event
    Lambda->>DDB: Query scan_id (partition key)

    alt Scan found
        DDB-->>Lambda: Scan item
        Lambda-->>APIGW: 200 OK + AnalysisReport
        APIGW-->>FE: AnalysisReport
        FE-->>User: Results page
    else Not found / expired
        DDB-->>Lambda: Empty result
        Lambda-->>APIGW: 404 Not Found
        APIGW-->>FE: { "detail": "Scan not found" }
        FE-->>User: Error message + Back to home
    end
```

---

## Diagram 3 — User Interaction

Shows every screen and decision the user encounters from landing on the site
through to viewing results.

```mermaid
flowchart TD
    START([User opens\nimgapp.craftingnewtech.com])

    subgraph Home ["Home Page"]
        LANDING["Landing Page\n─────────────────\nDocker Image Analyzer\n\n[ Analyze Dockerfile ]  [ Analyze Image ]"]
    end

    START --> LANDING

    LANDING -->|"Click\nAnalyze Dockerfile"| DF_FORM
    LANDING -->|"Click\nAnalyze Image"| IMG_FORM

    subgraph DockerfileFlow ["Dockerfile Analysis Flow"]
        DF_FORM["Dockerfile Form\n─────────────────\nText area: paste Dockerfile content\n\n[ Analyze ]"]

        DF_VALIDATE{"Content\nprovided?"}
        DF_ERROR_EMPTY["Inline error:\nDockerfile content is required"]

        DF_LOADING["Loading Spinner\n─────────────────\nAnalyzing your Dockerfile..."]

        DF_RESULTS["Results Page — Dockerfile\n─────────────────\nScore gauge (0–100)\nErrors count · Warnings count · Info count\n─────────────────\nFINDINGS\n  [ERROR] R001 — Unpinned base image\n    Description + Fix snippet\n  [ERROR] R002 — No USER instruction\n    Description + Fix snippet\n  [WARNING] R003 — No HEALTHCHECK\n    Description + Fix snippet\n  ...\n─────────────────\nFIXED DOCKERFILE\n  FROM ubuntu:22.04\n  RUN apt-get update && apt-get install...\n  USER 1000\n  HEALTHCHECK ...\n─────────────────\nMETADATA\n  instruction_count · stage_count\n  has_healthcheck · has_non_root_user\n─────────────────\nScan ID · Created · Completed"]

        DF_PERFECT["Results Page — Perfect Score\n─────────────────\nScore: 100\nErrors: 0 · Warnings: 0\n─────────────────\nNo findings — great Dockerfile!\n─────────────────\nMETADATA"]
    end

    DF_FORM -->|"Click Analyze"| DF_VALIDATE
    DF_VALIDATE -->|"No"| DF_ERROR_EMPTY
    DF_ERROR_EMPTY --> DF_FORM
    DF_VALIDATE -->|"Yes"| DF_LOADING
    DF_LOADING -->|"Findings found"| DF_RESULTS
    DF_LOADING -->|"Score = 100"| DF_PERFECT

    subgraph ImageFlow ["Image Analysis Flow"]
        IMG_FORM["Image Form\n─────────────────\nInput: image name\ne.g. nginx:1.25-alpine\n\n[ Analyze ]"]

        IMG_VALIDATE{"Image name\nprovided?"}
        IMG_ERROR_EMPTY["Inline error:\nImage name is required"]

        IMG_LOADING["Loading Spinner\n─────────────────\nFetching image metadata..."]

        IMG_RESULTS["Results Page — Image\n─────────────────\nLayers count badge\n─────────────────\nIMAGE\n  library/nginx:1.25-alpine\nDIGEST\n  sha256:abc123...\n─────────────────\nMETADATA\n  architecture · os\n  compressed_size_bytes\n  tag_status · last_pushed\n─────────────────\nScan ID · Created · Completed"]

        IMG_ERROR_404["Error state\n─────────────────\nImage not found on Docker Hub\n\n[ Back to home ]"]

        IMG_ERROR_502["Error state\n─────────────────\nFailed to reach Docker Hub\n\n[ Back to home ]"]
    end

    IMG_FORM -->|"Click Analyze"| IMG_VALIDATE
    IMG_VALIDATE -->|"No"| IMG_ERROR_EMPTY
    IMG_ERROR_EMPTY --> IMG_FORM
    IMG_VALIDATE -->|"Yes"| IMG_LOADING
    IMG_LOADING -->|"Image found"| IMG_RESULTS
    IMG_LOADING -->|"404 — not found"| IMG_ERROR_404
    IMG_LOADING -->|"502 — upstream error"| IMG_ERROR_502

    subgraph Navigation ["Navigation"]
        BACK["← New analysis\n(header link)"]
    end

    DF_RESULTS --> BACK
    DF_PERFECT --> BACK
    IMG_RESULTS --> BACK
    IMG_ERROR_404 --> BACK
    IMG_ERROR_502 --> BACK
    BACK --> LANDING
```

---

## Rendering These Diagrams

**GitHub** — renders Mermaid automatically in any `.md` file.

**VS Code** — install the *Markdown Preview Mermaid Support* extension.

**Locally** — use the [Mermaid Live Editor](https://mermaid.live) — paste any diagram block to preview and export as PNG or SVG.

**Export to PNG/SVG for use in presentations:**
1. Open [mermaid.live](https://mermaid.live)
2. Paste the diagram code (without the triple-backtick fences)
3. Click **Export** → PNG or SVG
