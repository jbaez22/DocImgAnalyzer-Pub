# DocImgAnalizer — User Guide v2

## What Is New in v2?

Phase 2 adds **user accounts** and **deep vulnerability scanning**. You can now:

- Create an account and sign in
- Submit any Docker image for a full CVE scan (Trivy) and SBOM generation (Syft)
- View your complete scan history
- Download CVE reports and CycloneDX SBOMs

**Phase 1 anonymous flows remain fully functional** — Dockerfile analysis and image metadata
lookup do not require an account.

**Endpoints**

| Interface | URL |
|-----------|-----|
| Frontend (browser) | `https://imgapp.craftingnewtech.com` |
| REST API v1 (anonymous) | `https://img.craftingnewtech.com/api/v1/` |
| REST API v2 (authenticated) | `https://img.craftingnewtech.com/api/v2/` |

---

## Creating an Account

1. Open `https://imgapp.craftingnewtech.com` and click **Sign Up**
2. Enter your email address and a password (minimum 12 characters, must include uppercase,
   lowercase, number, and symbol)
3. Check your inbox for a verification email from Cognito and click the link
4. Sign in with your email and password

**Forgot your password?** Click **Forgot password** on the sign-in page. A reset link will
be sent to your verified email address.

---

## Deep Image Scan (v2)

The deep scan runs Trivy (CVE detection) and Syft (SBOM generation) on any Docker image.
It is asynchronous — results are available within 1–5 minutes depending on image size.

### Via the Frontend

1. Sign in to your account
2. Click **Deep Scan** on the home page
3. Enter a Docker image reference (e.g., `nginx:1.25-alpine`)
4. Click **Scan** — you will see a status indicator: **Pending → Processing → Complete**
5. When complete, the results page shows:
   - **CVE table** — findings grouped by severity (CRITICAL / HIGH / MEDIUM / LOW)
   - **SBOM download** — CycloneDX JSON with all detected packages
   - **Counts** — total CVE count by severity

### Via the REST API

**Step 1 — Authenticate and get an access token**

```bash
# Exchange credentials for Cognito tokens
TOKEN=$(aws cognito-idp initiate-auth \
  --auth-flow USER_PASSWORD_AUTH \
  --client-id <your-app-client-id> \
  --auth-parameters USERNAME=you@example.com,PASSWORD=yourpassword \
  --query 'AuthenticationResult.AccessToken' \
  --output text)
```

Or use [AWS Amplify Auth](https://docs.amplify.aws/react/build-a-backend/auth/) in your
frontend application.

**Step 2 — Submit a deep scan**

```bash
curl -s -X POST https://img.craftingnewtech.com/api/v2/analyze/image \
  -H "Authorization: Bearer $TOKEN" \
  -H "Content-Type: application/json" \
  -d '{"image_name": "nginx:1.25-alpine"}' | jq .
```

**Response (HTTP 202)**
```json
{
  "scan_id": "a1b2c3d4-...",
  "status": "PENDING",
  "message": "Scan submitted — poll /api/v2/results/{scan_id} for status"
}
```

**Step 3 — Poll for results**

```bash
curl -s https://img.craftingnewtech.com/api/v2/results/a1b2c3d4-... \
  -H "Authorization: Bearer $TOKEN" | jq .
```

**Response when complete**
```json
{
  "scan_id": "a1b2c3d4-...",
  "scan_type": "image",
  "status": "COMPLETE",
  "image_name": "nginx:1.25-alpine",
  "created_at": "2026-06-22T18:00:00Z",
  "cve_critical": 0,
  "cve_high": 2,
  "cve_medium": 14,
  "cve_low": 31,
  "report_url": "https://...",
  "sbom_url": "https://..."
}
```

Possible values for `status`: `PENDING`, `PROCESSING`, `COMPLETE`, `FAILED`.

---

## Authenticated Dockerfile Analysis (v2)

Authenticated Dockerfile analysis works the same as the anonymous v1 endpoint, but results
are stored in your account history without TTL expiry.

```bash
curl -s -X POST https://img.craftingnewtech.com/api/v2/analyze/dockerfile \
  -H "Authorization: Bearer $TOKEN" \
  -H "Content-Type: application/json" \
  -d '{
    "content": "FROM python:3.12-slim\nWORKDIR /app\nCOPY . .\nUSER 1000\nHEALTHCHECK CMD true\nCMD [\"python\", \"main.py\"]"
  }' | jq .
```

---

## Scan History

View all your past scans:

```bash
curl -s https://img.craftingnewtech.com/api/v2/scans \
  -H "Authorization: Bearer $TOKEN" | jq .
```

**Response**
```json
{
  "scans": [
    {
      "scan_id": "a1b2c3d4-...",
      "scan_type": "image",
      "status": "COMPLETE",
      "created_at": "2026-06-22T18:00:00Z",
      "image_name": "nginx:1.25-alpine"
    }
  ],
  "next_page_token": null
}
```

**Delete a scan**

```bash
curl -s -X DELETE https://img.craftingnewtech.com/api/v2/scans/a1b2c3d4-... \
  -H "Authorization: Bearer $TOKEN"
```

Returns HTTP 204 on success.

---

## Health Check

```bash
curl https://img.craftingnewtech.com/api/v2/health
```

```json
{"status": "ok", "version": "2"}
```

---

## Token Expiry and Refresh

| Token | Expiry |
|-------|--------|
| Access token | 60 minutes |
| Refresh token | 30 days |

When the access token expires, use the refresh token to obtain a new one:

```bash
NEW_TOKEN=$(aws cognito-idp initiate-auth \
  --auth-flow REFRESH_TOKEN_AUTH \
  --client-id <your-app-client-id> \
  --auth-parameters REFRESH_TOKEN=<your-refresh-token> \
  --query 'AuthenticationResult.AccessToken' \
  --output text)
```

---

## Data Retention

| Scan type | Retention |
|-----------|----------|
| Authenticated scan (v2) | Indefinite (until you delete it) |
| Anonymous Dockerfile scan (v1) | 90 days (Phase 1 TTL) |

CVE reports and SBOMs are stored in S3 with a 365-day lifecycle policy.

---

## Error Codes

| HTTP Code | Meaning |
|-----------|---------|
| 401 | Missing, expired, or invalid JWT |
| 403 | Token valid but accessing another user's scan |
| 404 | Scan ID not found |
| 422 | Request body validation failed |
| 502 | Upstream error (Docker Hub, scanner) |
| 503 | Service temporarily unavailable |

---

*DocImgAnalizer Phase 2 — craftingnewtech.com*
