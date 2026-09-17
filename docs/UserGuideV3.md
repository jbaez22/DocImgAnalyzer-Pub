# Docker Image Analyzer — User Guide V3

**Version:** 3.0  
**Last updated:** 2026-07-07  
**Applies to:** Phase 3 (Stripe billing, API keys, organization accounts)  
**API base:** `https://img.craftingnewtech.com`  
**App URL:** `https://imgapp.craftingnewtech.com`

---

## Table of Contents

1. [Overview](#1-overview)
2. [Subscription Tiers](#2-subscription-tiers)
3. [Getting Started — Creating an Account](#3-getting-started--creating-an-account)
4. [Signing In and Out](#4-signing-in-and-out)
5. [Dockerfile Analysis (Free — No Account Required)](#5-dockerfile-analysis-free--no-account-required)
6. [Deep Image Scanning (Pro and Enterprise)](#6-deep-image-scanning-pro-and-enterprise)
7. [Viewing Scan Results](#7-viewing-scan-results)
8. [Scan History and Trends](#8-scan-history-and-trends)
9. [Upgrading Your Plan](#9-upgrading-your-plan)
10. [Managing Your Billing](#10-managing-your-billing)
11. [API Keys (Pro and Enterprise)](#11-api-keys-pro-and-enterprise)
12. [CI/CD Integration — GitHub Action](#12-cicd-integration--github-action)
13. [Organization Accounts (Enterprise)](#13-organization-accounts-enterprise)
14. [EventBridge Auto Re-scanning (Pro and Enterprise)](#14-eventbridge-auto-re-scanning-pro-and-enterprise)
15. [Security and Privacy](#15-security-and-privacy)
16. [Troubleshooting](#16-troubleshooting)

---

## 1. Overview

Docker Image Analyzer scans your Dockerfiles and container images for:

- **Security vulnerabilities (CVEs)** — powered by Trivy, updated daily
- **Dockerfile best-practice violations** — 11 rules covering secrets, base images, caching, and more
- **Software Bill of Materials (SBOM)** — full component inventory in CycloneDX JSON format (Pro/Enterprise)

All results are assigned a **security score (0–100)**. A score of 100 means no findings.

| Feature | Free | Pro | Enterprise |
|---------|------|-----|-----------|
| Dockerfile analysis | Unlimited | Unlimited | Unlimited |
| Deep image scan (CVE + SBOM) | — | 200/month | Unlimited |
| Scan history | 30 days | 1 year | Unlimited |
| API key access | — | 1 key | 10 keys |
| Organization seats | — | — | Up to 20 |
| Auto re-scanning | — | Yes | Yes |

---

## 2. Subscription Tiers

| Tier | Price | Best for |
|------|-------|---------|
| **Free** | $0/month | Individuals exploring Dockerfile quality |
| **Pro** | $19/month | Developers running regular image scans in CI/CD |
| **Enterprise** | $99/month | Teams that share scan quotas and need bulk API access |

You can upgrade, downgrade, or cancel at any time. Changes take effect at the next billing cycle. Cancellation reverts your account to Free immediately after the current period ends.

---

## 3. Getting Started — Creating an Account

1. Go to **`https://imgapp.craftingnewtech.com/sign-up`**
2. Enter your **email address** and choose a **password**
   - Password must be at least 8 characters and include one uppercase letter, one number, and one special character
3. Click **Create Account**
4. Check your inbox for a **verification code** from `no-reply@craftingnewtech.com`
5. Enter the 6-digit code on the confirmation screen
6. You are now signed in on the **Free tier**

> **Tip:** If the verification email doesn't arrive within 2 minutes, check your spam folder or click **Resend Code**.

---

## 4. Signing In and Out

**Sign in:**
1. Go to **`https://imgapp.craftingnewtech.com/sign-in`**
2. Enter your email and password
3. Click **Sign In** — you will be redirected to your Dashboard

**Forgot password:**
1. Click **Forgot password?** on the sign-in page
2. Enter your email — a reset code will be sent
3. Enter the code and choose a new password

**Sign out:**
- Click your avatar or email address in the top-right navigation bar
- Select **Sign Out**

---

## 5. Dockerfile Analysis (Free — No Account Required)

Dockerfile analysis is available to everyone — no account needed.

**Via the web app:**
1. Go to **`https://imgapp.craftingnewtech.com`**
2. Paste your Dockerfile content into the text area
3. Click **Analyze**
4. Results appear within seconds — score, findings list, and a fixed Dockerfile

**Via the API (no auth required):**
```bash
curl -X POST https://img.craftingnewtech.com/api/v1/analyze \
  -H "Content-Type: application/json" \
  -d '{"dockerfile": "FROM ubuntu:latest\nRUN apt-get install curl\n"}'
```

**Understanding the score:**

| Score | Rating | Meaning |
|-------|--------|---------|
| 90–100 | Excellent | Minor or no issues |
| 70–89 | Good | A few warnings to address |
| 50–69 | Fair | Multiple issues present |
| Below 50 | Poor | Critical security problems — do not deploy |

**Rule reference (11 rules):**

| Rule | Severity | Issue |
|------|----------|-------|
| R001 | ERROR | `:latest` tag or no tag on `FROM` |
| R002 | ERROR | No `USER` instruction or `USER root` |
| R003 | WARNING | No `HEALTHCHECK` |
| R004 | ERROR | Secret key name in `ENV` or `ARG` |
| R005 | ERROR | `curl`/`wget` piped to `bash`/`sh` |
| R006 | WARNING | `ADD` used for local files instead of `COPY` |
| R007 | WARNING | More than one `RUN` instruction |
| R008 | WARNING | Single-stage build (not `scratch`) |
| R009 | WARNING | Non-minimal final base image |
| R010 | WARNING | Package cache not cleaned |
| R011 | WARNING | `npm install` instead of `npm ci` |

---

## 6. Deep Image Scanning (Pro and Enterprise)

Deep scanning pulls a container image and runs a full CVE scan (Trivy) and SBOM generation (Syft). Results are stored in your scan history.

**Requirements:** Active Pro or Enterprise subscription + signed in.

**Via the web app:**
1. Sign in and go to your **Dashboard**
2. Click **New Scan**
3. Enter the full image name with tag, e.g. `nginx:1.25.3` or `myrepo/myapp:v2.1.0`
4. Click **Start Scan**
5. The scan is queued — status shows **PENDING**, then **PROCESSING**
6. When complete (typically 1–3 minutes), status changes to **COMPLETE**
7. Click the scan row to view full results

**Private registry images:**
- The scanner uses the ECS task role — it can pull images from your account's ECR repositories automatically
- For Docker Hub private images, contact support to configure pull credentials

**Scan statuses:**

| Status | Meaning |
|--------|---------|
| PENDING | In the queue, not yet started |
| PROCESSING | Trivy + Syft running against the image |
| COMPLETE | Results available |
| FAILED | Scan could not complete — check image name and retry |

---

## 7. Viewing Scan Results

After a scan completes, click on any scan in your Dashboard to open the results page.

**CVE Table:**

| Column | Description |
|--------|-------------|
| Severity | CRITICAL / HIGH / MEDIUM / LOW |
| Package | Affected library name and version |
| CVE ID | Clickable link to NVD entry |
| Fixed in | Version that resolves the vulnerability (if available) |
| Description | Brief summary of the vulnerability |

Results are sorted by severity (CRITICAL first). Use the column headers to re-sort.

**SBOM Download:**

- Click **Download SBOM (CycloneDX JSON)** to download the full Software Bill of Materials
- The SBOM lists every package in the image — useful for compliance, audits, and license checks
- The download link is valid for **1 hour**; return to the scan page to generate a fresh link

**Score breakdown:**

- The score shown is the **Dockerfile score** (from Rule Engine analysis)
- The CVE panel shows image vulnerability counts separately
- A score of 100 with 0 CRITICAL/HIGH CVEs is the goal

---

## 8. Scan History and Trends

**Scan history:**
1. Navigate to **Scans** in the top navigation
2. All your scans are listed with image name, date, status, and CVE counts
3. Use the date filter and status filter to narrow results
4. Click any row to open the full result

**Score trend (Pro and Enterprise):**
1. Navigate to **Trends**
2. Select an image name from the dropdown — only images you have scanned appear
3. The chart shows your score over time for that image
4. Hover over any data point to see the date and exact score
5. Use the trend to track security improvements as you update base images and fix CVEs

**History retention by tier:**

| Tier | Retention |
|------|-----------|
| Free | 30 days |
| Pro | 1 year |
| Enterprise | Unlimited |

Scans older than the retention window are automatically deleted.

---

## 9. Upgrading Your Plan

1. Sign in and navigate to **Pricing** (`/pricing`) or click the **Upgrade** button in the nav bar
2. Click **Get Pro** or **Get Enterprise**
3. You are redirected to the **Stripe Checkout page** — a secure Stripe-hosted payment form
4. Enter your payment details and click **Subscribe**
5. You are returned to the app — your new tier is active within seconds
6. A confirmation email is sent from Stripe

**Payment methods accepted:** Visa, Mastercard, American Express, Discover (via Stripe).

> Your payment details are handled entirely by Stripe — Docker Image Analyzer never stores or sees your card number.

---

## 10. Managing Your Billing

Navigate to **Billing** (`/billing`) to see:

- Your current plan and next renewal date
- Scans used this month vs. your monthly limit
- A link to the **Stripe Customer Portal**

**Stripe Customer Portal lets you:**
- Update payment method
- View past invoices and download receipts
- Upgrade or downgrade your plan
- Cancel your subscription

To open the portal: click **Manage Billing** on the Billing page — you are redirected to Stripe's hosted portal and returned to the app when done.

---

## 11. API Keys (Pro and Enterprise)

API keys let you call the API from scripts and CI/CD pipelines without a user session.

### Creating an API Key

1. Navigate to **API Keys** (`/keys`)
2. Click **Create New Key**
3. Enter a name for the key (e.g., `github-ci`, `jenkins-prod`)
4. Click **Create**
5. **Copy the key immediately** — it is shown only once and cannot be retrieved again
6. Store it securely (e.g., GitHub Actions secret, AWS Secrets Manager)

The key format is: `dia_<64 hex characters>`

### Using an API Key

Pass the key in the `X-Api-Key` request header:

```bash
curl -X POST https://img.craftingnewtech.com/api/v3/analyze/dockerfile \
  -H "X-Api-Key: dia_your_key_here" \
  -H "Content-Type: application/json" \
  -d '{"dockerfile": "FROM node:18-alpine\n..."}'
```

### Revoking an API Key

1. Navigate to **API Keys** (`/keys`)
2. Find the key by name
3. Click **Revoke** — the key is immediately invalidated
4. Any CI/CD jobs using the revoked key will receive `401 Unauthorized`

### Key Limits by Tier

| Tier | Active keys |
|------|------------|
| Free | 0 |
| Pro | 1 |
| Enterprise | 10 |

---

## 12. CI/CD Integration — GitHub Action

The official GitHub Action lets you analyze Dockerfiles in any repository as part of your CI pipeline.

### Setup

1. Store your API key as a GitHub repository secret named `DOCKER_ANALYZER_KEY`
   - Settings → Secrets and variables → Actions → New repository secret

2. Add the action to your workflow:

```yaml
# .github/workflows/security.yml
name: Dockerfile Security Check

on: [push, pull_request]

jobs:
  analyze:
    runs-on: ubuntu-latest
    steps:
      - uses: actions/checkout@v4

      - name: Analyze Dockerfile
        uses: jbaez22/docker-analyzer-action@v1
        with:
          api-key: ${{ secrets.DOCKER_ANALYZER_KEY }}
          dockerfile: ./Dockerfile          # path to your Dockerfile
          fail-on-score-below: 80           # fail if score drops below 80
          fail-on-severity: HIGH            # fail if any HIGH or CRITICAL CVE found
```

### Action Inputs

| Input | Required | Default | Description |
|-------|----------|---------|-------------|
| `api-key` | Yes | — | Your Docker Image Analyzer API key |
| `dockerfile` | No | `./Dockerfile` | Path to the Dockerfile to analyze |
| `fail-on-score-below` | No | `0` (disabled) | Fail the build if score is below this value |
| `fail-on-severity` | No | `none` | Fail on `CRITICAL`, `HIGH`, `MEDIUM`, or `LOW` CVEs |

### Action Outputs

| Output | Description |
|--------|-------------|
| `score` | Dockerfile security score (0–100) |
| `critical-count` | Number of CRITICAL CVEs found |
| `high-count` | Number of HIGH CVEs found |
| `scan-id` | Scan ID for retrieving full results via API |

### Example Step Summary

The action posts a summary to the GitHub Actions step summary tab:

```
Docker Image Analyzer — Results
================================
Score: 72/100

Findings:
  [ERROR] R001: Base image uses :latest tag (-20 pts)
  [ERROR] R002: No USER instruction — container runs as root (-25 pts)
  [WARNING] R003: No HEALTHCHECK instruction (-10 pts)

CVE Summary: 0 CRITICAL, 2 HIGH, 8 MEDIUM, 14 LOW
Scan ID: 3f7a1c2d-...
```

---

## 13. Organization Accounts (Enterprise)

Organizations allow multiple team members to share a single Enterprise subscription and scan quota.

### Creating an Organization

1. Navigate to **Organization** (`/org`) — available to Enterprise subscribers only
2. Click **Create Organization**
3. Enter your organization name
4. Click **Create** — you become the org admin

### Inviting Members

1. Go to **Organization** → **Members**
2. Click **Invite Member**
3. Enter the member's email address
4. Click **Send Invite**
5. The invitee receives an email with a link to accept
6. Once accepted, they appear in your member list and share the org's scan quota

### Managing Members

- **Remove a member:** Click **Remove** next to their name — their access is revoked immediately
- **Quota sharing:** All org members draw from the same monthly scan pool (Enterprise: unlimited)
- **Admin transfer:** Contact support to transfer org admin to another member

### Org Limits

| | Enterprise |
|-|-----------|
| Max members | 20 |
| Shared scan quota | Unlimited |
| API keys per member | 10 (each member manages their own) |

---

## 14. EventBridge Auto Re-scanning (Pro and Enterprise)

Auto re-scanning checks your tracked images every day against the latest Trivy CVE database.
If a new vulnerability is found in an image you are tracking, you will receive an email alert.

### Enabling Auto Re-scan for an Image

1. Navigate to **Scans** and open any completed scan result
2. Click **Enable Auto Re-scan**
3. The toggle turns on — the image will be checked daily at 02:00 UTC

### What Happens on Re-scan

1. EventBridge Scheduler fires at 02:00 UTC
2. All images with auto re-scan enabled are queued to the ECS Fargate scanner
3. Results are written to your scan history
4. If new CRITICAL or HIGH CVEs are found that were not in the previous scan, an email alert is sent

### Disabling Auto Re-scan

1. Open any scan result for that image
2. Click **Disable Auto Re-scan**
3. The image is removed from the daily queue

---

## 15. Security and Privacy

- **Authentication:** Amazon Cognito — passwords are never stored or seen by Docker Image Analyzer
- **Payment data:** Handled entirely by Stripe — card numbers never touch our servers
- **API keys:** Only the SHA-256 hash of your key is stored; the raw key cannot be recovered by anyone, including our team
- **Scan data:** CVE reports and SBOMs are stored in S3, encrypted at rest with AES-256 (AWS KMS CMK)
- **Data retention:** Scan results are retained per your tier (30 days / 1 year / unlimited). You can delete individual scans at any time from your scan history
- **Image access:** The scanner only pulls publicly available images or images in your account's ECR. It does not store image layers

---

## 16. Troubleshooting

### I did not receive my verification email

- Check your spam/junk folder
- Wait 2 minutes and click **Resend Code** on the confirmation screen
- Ensure you are checking the inbox for the email address you signed up with

### My scan is stuck on PENDING or PROCESSING

- Scans typically complete in 1–3 minutes
- If a scan has been PROCESSING for more than 10 minutes, the scanner may have encountered an error pulling the image
- Check that the image name and tag are correct (e.g. `nginx:1.25.3` not `nginx:latest` which is blocked by R001 rules)
- Try submitting the scan again — if it fails again, contact support with the Scan ID

### I get 403 Forbidden on `/api/v3/analyze/image`

- Deep image scanning requires a Pro or Enterprise subscription
- Verify your plan on the **Billing** page
- If you recently upgraded, sign out and sign back in to refresh your session token

### I get 429 Too Many Requests

- You have reached your monthly scan limit
- Upgrade your plan on the **Pricing** page for a higher or unlimited quota
- Your quota resets at the start of each billing period (shown on the Billing page)

### My API key returns 401 Unauthorized

- Verify you are passing the key in the `X-Api-Key` header (not `Authorization`)
- Confirm the key has not been revoked on the **API Keys** page
- Ensure your subscription is still active — a lapsed Pro subscription deactivates API key access

### I cannot sign in after resetting my password

- Passwords must meet complexity requirements (8+ chars, uppercase, number, special character)
- Clear your browser cache and try again in an incognito window
- If the issue persists, contact support

### Stripe Checkout redirected me back without completing payment

- This typically means the payment was declined — check with your bank or try a different card
- Your plan has not changed — you will not be charged for a failed checkout

---

*Docker Image Analyzer — craftingnewtech.com*  
*For support: you@example.com*
