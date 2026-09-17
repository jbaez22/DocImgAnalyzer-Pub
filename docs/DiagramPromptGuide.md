# Architecture Diagram Prompt Guide

Reusable prompt template for generating AWS architecture diagrams using the
`diagrams` Python library (mingrammer/diagrams). Produces PNG output with
official AWS icons and a clean horizontal layout.

---

## Prompt Template

```
Generate a Python script using the `diagrams` library (mingrammer/diagrams)
that produces a PNG architecture diagram with the following requirements:

TOOL & OUTPUT
- Library: mingrammer/diagrams (already installed)
- Output: PNG via Graphviz
- Run with: python3 <script>.py
- Save to: docs/diagrams/<name>.png

LAYOUT
- Direction: left-to-right (LR) — set both direction="LR" and
  graph_attr={"rankdir": "LR"}
- splines="ortho" for clean right-angle arrows
- nodesep="0.8", ranksep="1.4" for breathing room
- compound="true" in graph_attr so edges can cross cluster boundaries

ICONS
- Use official AWS icons from diagrams.aws.*
  (compute, network, database, storage, integration, security, management)
- User/browser: diagrams.onprem.client.User

CLUSTERS — USE SPARINGLY, only for real architectural boundaries:
- VPC is always a cluster (it is an infrastructure boundary)
  - Nest Private Subnets inside the VPC cluster
  - Put VPC Endpoints (Privatelink) as a node inside the VPC cluster
  - Put ECR inside the VPC cluster if it is only accessed from within
- Group compute by phase/tier if there are multiple phases
- Group data stores by phase/tier
- DO NOT over-cluster — flat nodes flow better in Graphviz

EDGES
- Label every arrow with what it actually does (PutItem, SendMessage, etc.)
- Use style="dashed" + color="#BBBBBB" for frozen/legacy paths
- Use color="#6f42c1" for auth flows (Cognito/JWT)
- Use color="#FF9900" for async/queue flows
- For any back-flowing edge (e.g., Lambda writes PENDING to DDB, Fargate
  writes COMPLETE to same DDB), add constraint="false" to prevent Graphviz
  from distorting the layout

READABILITY
- Node labels: service name on line 1, key config on lines 2-3 (version,
  key attributes). Max 4 lines.
- Cluster labels: zone name + key constraint
  (e.g., "VPC 10.0.0.0/16 · No NAT Gateway")
- Do not include CI/CD, Security panel, or Observability in the main diagram
  — those belong in a separate ops diagram
- Phase boundaries should be visible (frozen vs. active clusters)

ARCHITECTURE TO DIAGRAM:
[describe your architecture here — services, flow, VPC layout, async paths]
```

---

## The Three Rules That Matter Most

| # | Rule | Why |
|---|------|-----|
| 1 | **One cluster per real boundary** | VPC yes, "Phase 2 Compute" maybe, "Lambda group" no. Over-clustering breaks Graphviz automatic layout. |
| 2 | **`constraint="false"` on any back-flowing edge** | Prevents the double-writer problem — e.g., two services writing to the same DynamoDB table pulling it out of position. |
| 3 | **Label edges with verbs, not service names** | `PutItem PENDING`, `SendMessage`, `pull image` tells the reader *what happens*, not just *who connects to whom*. |

---

## Starter Script Template

```python
from diagrams import Diagram, Cluster, Edge
from diagrams.aws.compute import Lambda, ECR, Fargate
from diagrams.aws.database import Dynamodb
from diagrams.aws.storage import S3
from diagrams.aws.network import CloudFront, Route53, APIGateway, Privatelink
from diagrams.aws.integration import SQS
from diagrams.aws.security import Cognito
from diagrams.onprem.client import User

graph_attr = {
    "bgcolor": "white",
    "fontname": "Arial",
    "fontsize": "13",
    "pad": "1.0",
    "splines": "ortho",
    "nodesep": "0.8",
    "ranksep": "1.4",
    "rankdir": "LR",
    "compound": "true",
}
node_attr = {"fontname": "Arial", "fontsize": "10", "margin": "0.3"}
edge_attr = {"fontname": "Arial", "fontsize": "9",  "color": "#444444"}

with Diagram(
    "Your App — Architecture  |  AWS us-east-1",
    filename="docs/diagrams/your-diagram",
    direction="LR",
    show=False,
    graph_attr=graph_attr,
    node_attr=node_attr,
    edge_attr=edge_attr,
    outformat="png",
):
    user = User("User\nBrowser")

    with Cluster("Edge  ·  DNS + CDN"):
        r53 = Route53("Route 53")
        cf  = CloudFront("CloudFront\nOAC  WAF  TLS")
        fe  = S3("S3 Frontend")
        r53 >> cf >> fe

    with Cluster("API  ·  your-domain.com"):
        apigw = APIGateway("API Gateway  HTTP v2")

    with Cluster("VPC  10.0.0.0/16  ·  us-east-1\nNo NAT Gateway"):
        with Cluster("Private Subnets\n10.0.1.0/24  us-east-1a"):
            fargate = Fargate("ECS Fargate Task\nyour workload")
        ep = Privatelink("VPC Endpoints\nInterface + Gateway")
        ep >> Edge(style="dashed", color="#2E86C1") >> fargate

    with Cluster("Storage"):
        db  = Dynamodb("DynamoDB\ntable-name")
        bkt = S3("S3 Bucket")

    # --- connections ---
    user >> Edge(label="HTTPS") >> r53
    cf   >> Edge(label="API requests") >> apigw
    apigw >> fargate
    fargate >> Edge(label="PutItem") >> db
    fargate >> Edge(label="PutObject") >> bkt
```

---

## Common AWS Icon Imports

```python
# Compute
from diagrams.aws.compute import Lambda, ECS, Fargate, ECR, EC2

# Network
from diagrams.aws.network import (
    APIGateway, CloudFront, Route53,
    Privatelink, Endpoint,          # VPC Endpoints
    PrivateSubnet, PublicSubnet,    # Subnet icons (decorative)
    NATGateway, InternetGateway,
    ALB, NLB,
)

# Database
from diagrams.aws.database import Dynamodb, RDS, ElastiCache, Aurora

# Storage
from diagrams.aws.storage import S3

# Integration / Messaging
from diagrams.aws.integration import SQS, SNS, Eventbridge, StepFunctions

# Security
from diagrams.aws.security import Cognito, KMS, WAF, IAM, ACM

# Management / Observability
from diagrams.aws.management import Cloudwatch, CloudwatchAlarm, CloudwatchLogs

# Client (outside AWS)
from diagrams.onprem.client import User, Browser
```

---

## Edge Color Convention

| Color | Meaning |
|-------|---------|
| `#444444` (default dark gray) | Standard request / response |
| `#6f42c1` (purple) | Auth flow — Cognito / JWT |
| `#FF9900` (orange) | Async / queue flow — SQS, SNS |
| `#1a7f37` (green) | Write to storage / database |
| `#2E86C1` (blue) | Internal / VPC routing |
| `#BBBBBB` (light gray) + `style="dashed"` | Frozen / legacy / Phase 1 path |
| `#f85149` (red) | Error path / Dead Letter Queue |

---

## Known Graphviz Limitations

- **You cannot manually position nodes.** Graphviz controls placement based
  on edges and cluster nesting. Use `constraint="false"` to draw informational
  edges without affecting layout.
- **Deep cluster nesting increases layout complexity.** If the diagram looks
  scattered, flatten one level of clustering.
- **`splines="ortho"` can fail on dense graphs.** Fall back to
  `splines="curved"` or `splines="spline"` if arrows overlap badly.
- **Node label line breaks** use `\n` — keep each line under ~25 characters
  for readability at normal zoom.

---

*Tool: mingrammer/diagrams v0.25.1 · Graphviz 15.0.0 · AWS us-east-1*
