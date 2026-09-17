#!/usr/bin/env bash
# Post-deploy smoke test — verifies the live API is healthy and end-to-end flows work.
#
# Usage:
#   bash scripts/smoke-test.sh                                       # prod, no JWT tests
#   API_BASE_URL=https://dev-img.craftingnewtech.com bash scripts/smoke-test.sh  # dev
#   make smoke-test                                                  # prod
#   make smoke-test API_BASE_URL=https://dev-img.craftingnewtech.com # dev
#
# Phase 3 JWT tests run automatically when AWS credentials are available.
# Set TEST_EMAIL / TEST_PASSWORD to override the default e2e test user.
#
# Required env for Phase 3 tests:
#   COGNITO_USER_POOL_ID  (default: us-east-1_ABC-EXAMPLE-XXXX)
#   COGNITO_CLIENT_ID     (default: ABC-EXAMPLE-XXXX)
#   TEST_EMAIL            (default: e2e-test@example.com)
#   TEST_PASSWORD         (default: ABC-EXAMPLE-XXXX)

set -euo pipefail

API="${API_BASE_URL:-https://img.craftingnewtech.com}"

POOL_ID="${COGNITO_USER_POOL_ID:-us-east-1_ABC-EXAMPLE-XXXX}"
CLIENT_ID="${COGNITO_CLIENT_ID:-ABC-EXAMPLE-XXXX}"
TEST_EMAIL="${TEST_EMAIL:-e2e-test@example.com}"
TEST_PASSWORD="${TEST_PASSWORD:-ABC-EXAMPLE-XXXX}"
SUBSCRIPTIONS_TABLE="${SUBSCRIPTIONS_TABLE:-img-analyzer-dev-subscriptions}"

# ── Colors ────────────────────────────────────────────────────────────────────
GREEN='\033[0;32m'
RED='\033[0;31m'
YELLOW='\033[1;33m'
BOLD='\033[1m'
NC='\033[0m'

PASS=0
FAIL=0
SKIP=0

# ── Helpers ───────────────────────────────────────────────────────────────────
pass() { echo -e "  ${GREEN}PASS${NC} $1"; PASS=$((PASS + 1)); }
fail() { echo -e "  ${RED}FAIL${NC} $1"; echo -e "       ${YELLOW}$2${NC}"; FAIL=$((FAIL + 1)); }
skip() { echo -e "  ${YELLOW}SKIP${NC} $1 — $2"; SKIP=$((SKIP + 1)); }

http_get() {
  curl -sf --max-time 15 "$1" 2>&1 || echo "__CURL_FAILED__"
}

http_get_auth() {
  local url="$1"
  local token="$2"
  curl -sf --max-time 15 \
    -H "Authorization: Bearer ${token}" \
    "$url" 2>&1 || echo "__CURL_FAILED__"
}

http_post() {
  local url="$1"
  local body="$2"
  curl -sf --max-time 30 \
    -X POST "$url" \
    -H "Content-Type: application/json" \
    -d "$body" 2>&1 || echo "__CURL_FAILED__"
}

http_post_auth() {
  local url="$1"
  local body="$2"
  local token="$3"
  curl -sf --max-time 30 \
    -X POST "$url" \
    -H "Content-Type: application/json" \
    -H "Authorization: Bearer ${token}" \
    -d "$body" 2>&1 || echo "__CURL_FAILED__"
}

http_post_apikey() {
  local url="$1"
  local body="$2"
  local apikey="$3"
  curl -sf --max-time 30 \
    -X POST "$url" \
    -H "Content-Type: application/json" \
    -H "X-Api-Key: ${apikey}" \
    -d "$body" 2>&1 || echo "__CURL_FAILED__"
}

http_delete_auth() {
  local url="$1"
  local token="$2"
  curl -s --max-time 15 \
    -X DELETE \
    -H "Authorization: Bearer ${token}" \
    -o /dev/null \
    -w "%{http_code}" \
    "$url" 2>/dev/null || echo "000"
}

http_status() {
  curl -s --max-time 10 \
    -o /tmp/smoke_body.txt \
    -w "%{http_code}" \
    "$@" 2>/dev/null || echo "000"
}

contains() {
  echo "$1" | grep -q "$2"
}

# ── Test runner ───────────────────────────────────────────────────────────────
echo ""
echo -e "${BOLD}Docker Image Analyzer — Smoke Test${NC}"
echo -e "API endpoint: ${YELLOW}${API}${NC}"
echo "────────────────────────────────────────"

# ── 1. Health check ───────────────────────────────────────────────────────────
echo ""
echo -e "${BOLD}[1] Health${NC}"

HEALTH=$(http_get "${API}/api/v1/health")

if contains "$HEALTH" "__CURL_FAILED__"; then
  fail "GET /api/v1/health" "Could not reach API — is the endpoint correct and deployed?"
elif contains "$HEALTH" '"status"'; then
  pass "GET /api/v1/health → 200 OK"
else
  fail "GET /api/v1/health" "Unexpected response: ${HEALTH}"
fi

# ── 2. Dockerfile analysis (v1 — public, no auth) ────────────────────────────
echo ""
echo -e "${BOLD}[2] Dockerfile Analysis (v1 — public)${NC}"

DOCKERFILE_BODY='{"content":"FROM python:3.12\nWORKDIR /app\nCOPY . .\nRUN pip install -r requirements.txt\nCMD [\"python\",\"main.py\"]"}'
SCAN=$(http_post "${API}/api/v1/analyze/dockerfile" "$DOCKERFILE_BODY")

if contains "$SCAN" "__CURL_FAILED__"; then
  fail "POST /api/v1/analyze/dockerfile" "Request failed — is the Lambda running?"
elif contains "$SCAN" '"scan_id"'; then
  pass "POST /api/v1/analyze/dockerfile → scan returned"
  SCAN_ID=$(echo "$SCAN" | grep -o '"scan_id":"[^"]*"' | cut -d'"' -f4 || echo "")
else
  fail "POST /api/v1/analyze/dockerfile" "Unexpected response: ${SCAN}"
  SCAN_ID=""
fi

if [ -n "$SCAN" ] && ! contains "$SCAN" "__CURL_FAILED__"; then
  contains "$SCAN" '"score"'    && pass "Dockerfile scan contains score"    || fail "Dockerfile scan contains score"    "Missing 'score'"
  contains "$SCAN" '"findings"' && pass "Dockerfile scan contains findings" || fail "Dockerfile scan contains findings" "Missing 'findings'"
fi

# ── 3. Results retrieval (v1) ─────────────────────────────────────────────────
echo ""
echo -e "${BOLD}[3] Results Retrieval (v1)${NC}"

if [ -n "${SCAN_ID:-}" ]; then
  RESULT=$(http_get "${API}/api/v1/results/${SCAN_ID}")
  if contains "$RESULT" "__CURL_FAILED__"; then
    fail "GET /api/v1/results/${SCAN_ID}" "Request failed"
  elif contains "$RESULT" '"scan_id"'; then
    pass "GET /api/v1/results/{scan_id} → 200 OK"
  else
    fail "GET /api/v1/results/${SCAN_ID}" "Unexpected response: ${RESULT}"
  fi
  contains "$RESULT" '"status"' && pass "Result contains status field" || fail "Result contains status field" "Missing 'status'"
else
  skip "Results retrieval" "no scan_id from previous step"
fi

# ── 4. Image metadata (v1) ────────────────────────────────────────────────────
echo ""
echo -e "${BOLD}[4] Image Scan (v1 — public)${NC}"

IMAGE_BODY='{"image":"nginx:alpine"}'
IMG=$(http_post "${API}/api/v1/analyze/image" "$IMAGE_BODY")

if contains "$IMG" "__CURL_FAILED__"; then
  fail "POST /api/v1/analyze/image" "Request failed"
elif contains "$IMG" '"scan_id"'; then
  pass "POST /api/v1/analyze/image → 200 OK"
else
  fail "POST /api/v1/analyze/image" "Unexpected response: ${IMG}"
fi
contains "$IMG" '"metadata"' && pass "Image scan contains metadata" || fail "Image scan contains metadata" "Missing 'metadata'"

# ── 5. 404 handling ───────────────────────────────────────────────────────────
echo ""
echo -e "${BOLD}[5] Error Handling${NC}"

NOT_FOUND_CODE=$(http_status "${API}/api/v1/results/nonexistent-scan-id-00000000")
if [ "$NOT_FOUND_CODE" = "404" ]; then
  pass "GET /api/v1/results/unknown-id → 404 (expected)"
elif [ "$NOT_FOUND_CODE" = "000" ]; then
  fail "GET /api/v1/results/unknown-id" "Could not reach endpoint"
else
  fail "GET /api/v1/results/unknown-id" "Expected 404, got ${NOT_FOUND_CODE}"
fi

# ── 6. Phase 3 — JWT + v3 endpoints ──────────────────────────────────────────
echo ""
echo -e "${BOLD}[6] Phase 3 — JWT Auth & v3 Endpoints${NC}"

# Try to get a Cognito ID token using USER_PASSWORD_AUTH
JWT=""
if command -v aws &>/dev/null; then
  JWT=$(aws cognito-idp initiate-auth \
    --auth-flow USER_PASSWORD_AUTH \
    --auth-parameters "USERNAME=${TEST_EMAIL},PASSWORD=${TEST_PASSWORD}" \
    --client-id "${CLIENT_ID}" \
    --region us-east-1 \
    --query 'AuthenticationResult.IdToken' \
    --output text 2>/dev/null || echo "")
fi

if [ -z "$JWT" ] || [ "$JWT" = "None" ]; then
  skip "Phase 3 JWT tests" "could not obtain Cognito token — set TEST_EMAIL / TEST_PASSWORD or configure AWS credentials"
else
  echo -e "  Token acquired for ${TEST_EMAIL}"

  # Reset scan_count_month so quota never blocks repeated CI runs
  if command -v aws &>/dev/null && command -v python3 &>/dev/null; then
    _SUB=$(echo "${JWT}" | python3 -c "
import sys, base64, json
tok = sys.stdin.read().strip()
p = tok.split('.')[1] if '.' in tok else ''
p += '=' * (-len(p) % 4)
try: print(json.loads(base64.urlsafe_b64decode(p)).get('sub',''))
except Exception: pass
" 2>/dev/null || echo "")
    if [ -n "$_SUB" ]; then
      aws dynamodb update-item \
        --table-name "${SUBSCRIPTIONS_TABLE}" \
        --key "{\"user_id\":{\"S\":\"${_SUB}\"}}" \
        --update-expression "SET scan_count_month = :zero" \
        --expression-attribute-values '{":zero":{"N":"0"}}' \
        --region us-east-1 2>/dev/null || true
    fi
  fi

  # 6a. Billing status
  BILLING=$(http_get_auth "${API}/api/v3/billing/status" "$JWT")
  if contains "$BILLING" "__CURL_FAILED__"; then
    fail "GET /api/v3/billing/status" "Request failed"
  elif contains "$BILLING" '"tier"'; then
    TIER=$(echo "$BILLING" | grep -o '"tier":"[^"]*"' | cut -d'"' -f4 || echo "?")
    pass "GET /api/v3/billing/status → tier=${TIER}"
  else
    fail "GET /api/v3/billing/status" "Unexpected response: ${BILLING}"
  fi

  contains "$BILLING" '"scan_count_month"' && pass "billing/status has scan_count_month" || fail "billing/status has scan_count_month" "Missing field"
  contains "$BILLING" '"scan_limit"'       && pass "billing/status has scan_limit"       || fail "billing/status has scan_limit"       "Missing field"

  # 6b. Create API key
  KEY_BODY='{"name":"smoke-test-key"}'
  KEY_RESP=$(http_post_auth "${API}/api/v3/keys" "$KEY_BODY" "$JWT")
  if contains "$KEY_RESP" "__CURL_FAILED__"; then
    fail "POST /api/v3/keys" "Request failed"
    RAW_KEY=""
    KEY_ID=""
  elif contains "$KEY_RESP" '"raw_key"'; then
    pass "POST /api/v3/keys → API key created"
    RAW_KEY=$(echo "$KEY_RESP" | grep -o '"raw_key":"[^"]*"' | cut -d'"' -f4 || echo "")
    KEY_ID=$(echo "$KEY_RESP" | grep -o '"key_id":"[^"]*"' | cut -d'"' -f4 || echo "")
  else
    fail "POST /api/v3/keys" "Unexpected response: ${KEY_RESP}"
    RAW_KEY=""
    KEY_ID=""
  fi

  # 6c. List keys — verify the created key appears
  KEYS_RESP=$(http_get_auth "${API}/api/v3/keys" "$JWT")
  if contains "$KEYS_RESP" "__CURL_FAILED__"; then
    fail "GET /api/v3/keys" "Request failed"
  elif contains "$KEYS_RESP" '"keys"'; then
    pass "GET /api/v3/keys → key list returned"
    if [ -n "$KEY_ID" ] && contains "$KEYS_RESP" "$KEY_ID"; then
      pass "GET /api/v3/keys — new key appears in list"
    elif [ -n "$KEY_ID" ]; then
      fail "GET /api/v3/keys — new key appears in list" "key_id ${KEY_ID} not found in list"
    fi
  else
    fail "GET /api/v3/keys" "Unexpected response: ${KEYS_RESP}"
  fi

  # 6d. Dockerfile analysis via X-Api-Key auth (v3)
  if [ -n "$RAW_KEY" ]; then
    DF_BODY='{"content":"FROM node:20-alpine\nWORKDIR /app\nCOPY . .\nRUN npm ci\nCMD [\"node\",\"index.js\"]"}'
    DF_RESP=$(http_post_apikey "${API}/api/v3/analyze/dockerfile" "$DF_BODY" "$RAW_KEY")
    if contains "$DF_RESP" "__CURL_FAILED__"; then
      fail "POST /api/v3/analyze/dockerfile (X-Api-Key)" "Request failed"
    elif contains "$DF_RESP" '"scan_id"'; then
      SCORE=$(echo "$DF_RESP" | grep -o '"score":[0-9]*' | cut -d: -f2 || echo "?")
      pass "POST /api/v3/analyze/dockerfile (X-Api-Key) → score=${SCORE}"
    else
      fail "POST /api/v3/analyze/dockerfile (X-Api-Key)" "Unexpected response: ${DF_RESP}"
    fi
  else
    skip "POST /api/v3/analyze/dockerfile (X-Api-Key)" "no raw_key from key creation"
  fi

  # 6e. Dockerfile analysis via JWT (v3)
  DF_JWT_BODY='{"content":"FROM ubuntu:22.04\nRUN apt-get update && apt-get install -y curl\nCMD [\"/bin/bash\"]"}'
  DF_JWT_RESP=$(http_post_auth "${API}/api/v3/analyze/dockerfile" "$DF_JWT_BODY" "$JWT")
  if contains "$DF_JWT_RESP" "__CURL_FAILED__"; then
    fail "POST /api/v3/analyze/dockerfile (JWT)" "Request failed"
  elif contains "$DF_JWT_RESP" '"scan_id"'; then
    SCORE=$(echo "$DF_JWT_RESP" | grep -o '"score":[0-9]*' | cut -d: -f2 || echo "?")
    pass "POST /api/v3/analyze/dockerfile (JWT) → score=${SCORE}"
  else
    fail "POST /api/v3/analyze/dockerfile (JWT)" "Unexpected response: ${DF_JWT_RESP}"
  fi

  # 6f. Revoke the smoke-test API key (cleanup)
  if [ -n "$KEY_ID" ]; then
    DEL_CODE=$(http_delete_auth "${API}/api/v3/keys/${KEY_ID}" "$JWT")
    if [ "$DEL_CODE" = "204" ]; then
      pass "DELETE /api/v3/keys/${KEY_ID} → 204 (revoked)"
    else
      fail "DELETE /api/v3/keys/${KEY_ID}" "Expected 204, got ${DEL_CODE}"
    fi
  else
    skip "DELETE /api/v3/keys/{key_id}" "no key_id to revoke"
  fi

  # 6g. Revoked key should be rejected on analyze
  if [ -n "$RAW_KEY" ]; then
    DF_REVOKED_BODY='{"content":"FROM alpine:3.19\nCMD [\"sh\"]"}'
    REVOKED_CODE=$(http_status \
      -X POST "${API}/api/v3/analyze/dockerfile" \
      -H "Content-Type: application/json" \
      -H "X-Api-Key: ${RAW_KEY}" \
      -d "$DF_REVOKED_BODY")
    if [ "$REVOKED_CODE" = "401" ] || [ "$REVOKED_CODE" = "403" ]; then
      pass "Revoked key rejected on analyze → ${REVOKED_CODE}"
    else
      fail "Revoked key rejected on analyze" "Expected 401/403, got ${REVOKED_CODE}"
    fi
  else
    skip "Revoked key rejection check" "no raw_key"
  fi

fi

# ── Summary ───────────────────────────────────────────────────────────────────
echo ""
echo "────────────────────────────────────────"
TOTAL=$((PASS + FAIL + SKIP))
if [ "$FAIL" -eq 0 ]; then
  echo -e "${GREEN}${BOLD}All checks passed${NC}  (${PASS} passed, ${SKIP} skipped, ${TOTAL} total)"
  echo ""
  exit 0
else
  echo -e "${RED}${BOLD}${FAIL} of $((PASS + FAIL)) checks FAILED${NC}  (${SKIP} skipped)"
  echo ""
  exit 1
fi
