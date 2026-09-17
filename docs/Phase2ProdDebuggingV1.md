# Phase 2 — Production Debugging V1

Issues encountered and resolved during the initial production deployment of Phase 2 and Phase 3.

---

## Issue 1: Dashboard "Failed to fetch" on `GET /api/v2/scans`

**Date:** 2026-07-08  
**Environment:** Production — `imgapp.craftingnewtech.com`  
**Symptom:** After signing in, the dashboard scan list showed `Failed to fetch`. The billing banner (`GET /api/v3/billing/status`) loaded correctly. All other v3 endpoints worked.

### What "Failed to fetch" means

`TypeError: Failed to fetch` is a browser-level network error thrown by `fetch()` before any HTTP response is received. It is **not** an HTTP 4xx/5xx error — it means the browser blocked the request entirely, typically because a CORS preflight failed.

### Root Cause

`ANY /api/v2/{proxy+}` was configured on the API Gateway with `authorization_type = JWT`. The browser sends a CORS preflight `OPTIONS` request before any authenticated cross-origin request. Preflight requests carry **no `Authorization` header**, so the JWT authorizer rejected them with `HTTP 401`.

The browser sees a non-2xx preflight response and throws `TypeError: Failed to fetch` — it never sends the actual `GET` request.

```
Browser                   API Gateway                     JWT Authorizer
  |                            |                                |
  |  OPTIONS /api/v2/scans     |                                |
  |  (no Authorization header) |                                |
  |--------------------------->|                                |
  |                            |------- validate JWT ---------->|
  |                            |                          no token
  |                            |<-------- 401 Unauthorized -----|
  |<---------- 401 -----------|                                |
  |                            |
  |  TypeError: Failed to fetch  (browser blocks the GET)
```

### Why v3 worked but v2 didn't

Every v3 route uses a specific HTTP method (`GET /api/v3/billing/status`, `POST /api/v3/keys`, etc.). An `OPTIONS` preflight does not match any of those routes, so it falls through to the API-level CORS handler, which responds `200` automatically.

`ANY /api/v2/{proxy+}` matches ALL methods including `OPTIONS`, intercepting preflights before the API-level CORS handler can respond.

| Route | Method | OPTIONS preflight handling |
|---|---|---|
| `ANY /api/v2/{proxy+}` | All methods (incl. OPTIONS) | Caught by route → JWT auth → **401** |
| `GET /api/v3/billing/status` | GET only | Not matched → API CORS handler → **200** |

### Investigation Steps

1. Confirmed Lambda v2 was healthy (`GET /api/v2/health` → 200, direct invocation → 200).
2. Verified JWT authorizer was correctly configured for prod Cognito pool `us-east-1_ABC-EXAMPLE-XXXX`.
3. Confirmed alias `v2 → $LATEST` existed and the resource policy allowed API Gateway invocation.
4. Simulated browser CORS preflight with curl:
   ```bash
   curl -sv -X OPTIONS \
     -H "Origin: https://imgapp.craftingnewtech.com" \
     -H "Access-Control-Request-Method: GET" \
     -H "Access-Control-Request-Headers: authorization,content-type" \
     "https://img.craftingnewtech.com/api/v2/scans"
   # → HTTP/2 401  ← preflight blocked by JWT authorizer
   ```
5. Compared v3 OPTIONS preflight (same command, v3 path) → `200`. Inspected API Gateway route table and found the method difference.

### Fix

Added an explicit `OPTIONS /api/v2/{proxy+}` route with `authorization_type = NONE`, wired to the same Lambda v2 integration. FastAPI's `CORSMiddleware` handles the OPTIONS request and returns `200`.

**Terraform — `terraform/phase2/modules/lambda_v2/main.tf`:**

```hcl
resource "aws_apigatewayv2_route" "v2_options" {
  api_id    = var.phase1_api_id
  route_key = "OPTIONS /api/v2/{proxy+}"
  target    = "integrations/${aws_apigatewayv2_integration.lambda_v2.id}"
  # No authorization_type — NONE by default
}
```

Applied via AWS CLI immediately (no deploy needed, auto-deploy is on), then the route was imported into Terraform state and committed.

**Verification:**

```bash
# Preflight: was 401, now 200
curl -s -o /dev/null -w "%{http_code}" -X OPTIONS \
  -H "Origin: https://imgapp.craftingnewtech.com" \
  -H "Access-Control-Request-Method: GET" \
  -H "Access-Control-Request-Headers: authorization,content-type" \
  "https://img.craftingnewtech.com/api/v2/scans"
# 200

# Authenticated GET: 200 with scan list
curl -s -o /dev/null -w "%{http_code}" \
  -H "Authorization: Bearer $JWT" \
  "https://img.craftingnewtech.com/api/v2/scans"
# 200
```

### Lesson Learned

**Avoid `ANY` as the route method when JWT authorization is required.** `ANY` includes `OPTIONS`, which intercepts CORS preflights and blocks them. Use explicit HTTP methods instead:

```hcl
# Problematic — OPTIONS gets JWT-authorized
route_key = "ANY /api/v2/{proxy+}"

# Better — OPTIONS falls through to API-level CORS handler
route_key = "GET /api/v2/{proxy+}"
# (add POST, DELETE routes separately as needed)

# Or: keep ANY but add explicit OPTIONS escape hatch (this fix)
route_key = "OPTIONS /api/v2/{proxy+}"
authorization_type = "NONE"
```

---

## Issue 2: Prod Smoke Test Failing — Dev Cognito Tokens Rejected

**Date:** 2026-07-08  
**Environment:** Production pipeline (`deploy.yml` — prod job)  
**Symptom:** The smoke test step in the prod deploy job failed on all Phase 3 JWT-authenticated checks with 401 responses.

### Root Cause

`scripts/smoke-test.sh` defaulted to dev Cognito pool credentials:

```bash
POOL_ID="${COGNITO_USER_POOL_ID:-us-east-1_ABC-EXAMPLE-XXXX}"     # dev pool
CLIENT_ID="${COGNITO_CLIENT_ID:-ABC-EXAMPLE-XXXX}"  # dev client
```

The prod API Gateway JWT authorizer is configured for the prod Cognito pool (`us-east-1_ABC-EXAMPLE-XXXX`). Tokens issued by the dev pool were rejected with 401.

The `deploy.yml` prod smoke test step was not passing the `COGNITO_USER_POOL_ID`/`COGNITO_CLIENT_ID` environment variables, so the script fell back to the dev defaults.

### Fix

1. Created an e2e test user in the prod Cognito pool.
2. Added Cognito pool/client env vars to the prod smoke test step in `deploy.yml`:

```yaml
- name: Smoke test
  run: |
    API_BASE_URL="${{ steps.tf_out.outputs.api_endpoint }}" bash scripts/smoke-test.sh
  env:
    COGNITO_USER_POOL_ID: ${{ vars.VITE_COGNITO_USER_POOL_ID }}
    COGNITO_CLIENT_ID: ${{ vars.VITE_COGNITO_CLIENT_ID }}
```

These vars are set per-environment in the GitHub `production` environment settings.

---

## Issue 3: Prod Frontend Built with Dev Cognito IDs

**Date:** 2026-07-08  
**Environment:** Production pipeline  
**Symptom:** Prod frontend could not authenticate — Amplify was configured with dev Cognito pool IDs baked in at build time.

### Root Cause

The prod frontend build step in `deploy.yml` was missing `VITE_COGNITO_USER_POOL_ID` and `VITE_COGNITO_CLIENT_ID`. Vite bakes these into the bundle at build time. Without them, Amplify initialized with `undefined`, falling back to empty strings, causing all Cognito operations to fail silently or error.

### Fix

Added the Cognito vars to the prod frontend build step:

```yaml
- name: Build frontend
  run: npm ci --prefix frontend && npm run build --prefix frontend
  env:
    VITE_API_BASE_URL: https://img.craftingnewtech.com
    VITE_COGNITO_USER_POOL_ID: ${{ vars.VITE_COGNITO_USER_POOL_ID }}
    VITE_COGNITO_CLIENT_ID: ${{ vars.VITE_COGNITO_CLIENT_ID }}
```

The `production` GitHub Environment holds the prod-specific values:

| Variable | Value |
|---|---|
| `VITE_COGNITO_USER_POOL_ID` | `us-east-1_ABC-EXAMPLE-XXXX` |
| `VITE_COGNITO_CLIENT_ID` | `ABC-EXAMPLE-XXXX` |

---

## Issue 4: Blank Dashboard Page After CORS Fix

**Date:** 2026-07-09
**Environment:** Production — `imgapp.craftingnewtech.com`
**Symptom:** After the CORS preflight fix was deployed, signing in now landed on a completely blank white page instead of the dashboard. No error message was shown — the entire React component tree silently crashed.

### Root Cause

A field name mismatch between the TypeScript frontend type and the actual API response.

The frontend type `ScanListResponse` in `frontend/src/types/api.ts` declared:

```ts
interface ScanListResponse {
  items: ScanResult[]        // ← wrong
  next_token: string | null  // ← wrong
}
```

The v2 backend (`backend/v2/routers/scans.py`) actually returns:

```json
{ "scans": [...], "next_page_token": null }
```

With the mismatch, `data.items` was `undefined`. `DashboardPage` then called:

```ts
setScans(prev => token ? [...prev, ...data.items] : data.items)
// data.items === undefined → scans state becomes undefined
```

On the next render, `scans.length === 0` threw `TypeError: Cannot read properties of undefined (reading 'length')`. React had no error boundary, so the entire page went blank — no error message, no stack trace visible to the user.

### Why It Was Hidden Before

The mismatch existed since the code was written, but was invisible while the CORS preflight was returning 401. With CORS blocking the request, `listScans()` threw a network-level `TypeError: Failed to fetch` before any API response was processed — so the bad field names were never reached. The CORS fix allowed the response through for the first time, exposing the type mismatch.

### Investigation

1. Confirmed the dashboard was crashing silently (blank page = uncaught render error, not an API error).
2. Found `data.items` is `undefined` by comparing the TypeScript type against the actual curl response:
   ```bash
   curl -s -H "Authorization: Bearer $JWT" \
     "https://img.craftingnewtech.com/api/v2/scans" | python3 -m json.tool
   # → { "scans": [...], "next_page_token": null }
   ```
3. Traced the crash: `setScans(undefined)` → `scans.length` in render → `TypeError`.

### Fix

Updated `frontend/src/types/api.ts` to match the actual API response:

```ts
export interface ScanListResponse {
  scans: ScanResult[]
  next_page_token: string | null
}
```

Updated `DashboardPage.tsx` to use the corrected field names:

```ts
const data = await listScans(token)
setScans(prev => token ? [...prev, ...data.scans] : data.scans)
setNextToken(data.next_page_token)
```

### Lesson Learned

**TypeScript's `as` casts and `<Type>` generics don't validate at runtime.** `requestV2<ScanListResponse>(...)` tells TypeScript to trust the type — but if the API returns different field names, the type is silently wrong at runtime. The mismatch only surfaces when the code actually accesses the misnamed field.

For a PoC: always verify the TypeScript interface against a real `curl` of the endpoint before writing any component code that consumes it.

---

## Quick-Reference Diagnostic Commands

```bash
# Check CORS preflight for any v2 endpoint
curl -sv -X OPTIONS \
  -H "Origin: https://imgapp.craftingnewtech.com" \
  -H "Access-Control-Request-Method: GET" \
  -H "Access-Control-Request-Headers: authorization,content-type" \
  "https://img.craftingnewtech.com/api/v2/scans" 2>&1 | grep -E "HTTP/2|access-control"

# Get a prod JWT for the e2e test user
JWT=$(aws cognito-idp initiate-auth \
  --auth-flow USER_PASSWORD_AUTH \
  --auth-parameters "USERNAME=e2e-test@example.com,PASSWORD=ABC-EXAMPLE-XXXX" \
  --client-id "ABC-EXAMPLE-XXXX" \
  --region us-east-1 \
  --query 'AuthenticationResult.IdToken' \
  --output text)

# Call /api/v2/scans with prod JWT
curl -s \
  -H "Authorization: Bearer $JWT" \
  "https://img.craftingnewtech.com/api/v2/scans" | python3 -m json.tool

# List API Gateway routes and their auth config
aws apigatewayv2 get-routes --api-id ag4a2gbi54 \
  --query 'Items[].{RouteKey:RouteKey,AuthType:AuthorizationType}' \
  --output table

# Check Lambda v2 recent logs
aws logs tail /aws/lambda/img-analyzer-prod-api-v2 --since 1h --follow
```
