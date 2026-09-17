from app.models.schemas import Severity
from app.services import dockerfile_analyzer

GOOD_DOCKERFILE = """\
FROM python:3.12-slim
WORKDIR /app
COPY requirements.txt .
RUN pip install --no-cache-dir -r requirements.txt
COPY . .
USER 1000
HEALTHCHECK CMD python -c "import urllib.request; urllib.request.urlopen('http://localhost:8000/api/v1/health')"
CMD ["python", "-m", "uvicorn", "app.main:app", "--host", "0.0.0.0", "--port", "8000"]
"""

BAD_DOCKERFILE = """\
FROM python
RUN apt-get update
RUN pip install requests
RUN pip install boto3
RUN pip install fastapi
ENV PASSWORD=mysecret
ADD . /app
"""


def test_good_dockerfile_high_score():
    result = dockerfile_analyzer.analyze(GOOD_DOCKERFILE)
    assert result.score >= 80


def test_good_dockerfile_no_critical_findings():
    result = dockerfile_analyzer.analyze(GOOD_DOCKERFILE)
    error_findings = [f for f in result.findings if f.severity == Severity.error]
    assert not error_findings


def test_unpinned_base_image_detected():
    result = dockerfile_analyzer.analyze(BAD_DOCKERFILE)
    assert any(f.rule_id == "R001" for f in result.findings)


def test_no_user_detected():
    result = dockerfile_analyzer.analyze(BAD_DOCKERFILE)
    assert any(f.rule_id == "R002" for f in result.findings)


def test_no_healthcheck_detected():
    result = dockerfile_analyzer.analyze(BAD_DOCKERFILE)
    assert any(f.rule_id == "R003" for f in result.findings)


def test_secret_in_env_detected():
    result = dockerfile_analyzer.analyze(BAD_DOCKERFILE)
    finding = next((f for f in result.findings if f.rule_id == "R004"), None)
    assert finding is not None
    assert finding.severity == Severity.error


def test_r004_fixed_dockerfile_removes_secret_line():
    df = "FROM python:3.12-slim\nENV API_KEY=supersecret123\nUSER 1000\nHEALTHCHECK CMD true\n"
    result = dockerfile_analyzer.analyze(df)
    assert result.fixed_dockerfile is not None
    # The actual secret value must NOT appear anywhere in the fixed output
    assert "supersecret123" not in result.fixed_dockerfile
    # The ENV line itself must be gone — only a comment explaining removal should remain
    assert "ENV API_KEY" not in result.fixed_dockerfile
    assert (
        "API_KEY" in result.fixed_dockerfile
    )  # key name appears only in the R004 comment


def test_r004_compound_key_detected_and_removed():
    # DB_PASSWORD uses an underscore-prefixed word — \b would miss it; must still match
    df = "FROM python:3.12-slim\nENV DB_PASSWORD=supersecret123\nUSER 1000\nHEALTHCHECK CMD true\n"
    result = dockerfile_analyzer.analyze(df)
    # Finding must be raised
    assert any(f.rule_id == "R004" for f in result.findings)
    # Secret value must be absent from fixed output
    assert result.fixed_dockerfile is not None
    assert "supersecret123" not in result.fixed_dockerfile
    assert "ENV DB_PASSWORD" not in result.fixed_dockerfile


def test_add_instead_of_copy_detected():
    result = dockerfile_analyzer.analyze(BAD_DOCKERFILE)
    assert any(f.rule_id == "R006" for f in result.findings)


def test_multiple_run_detected():
    result = dockerfile_analyzer.analyze(BAD_DOCKERFILE)
    assert any(f.rule_id == "R007" for f in result.findings)


def test_pipe_install_detected():
    df = "FROM ubuntu:22.04\nRUN curl https://example.com/install.sh | bash\nUSER 1000\nHEALTHCHECK CMD true\n"
    result = dockerfile_analyzer.analyze(df)
    assert any(f.rule_id == "R005" for f in result.findings)


def test_explicit_root_user_detected():
    df = "FROM ubuntu:22.04\nUSER root\nHEALTHCHECK CMD true\n"
    result = dockerfile_analyzer.analyze(df)
    finding = next((f for f in result.findings if f.rule_id == "R002"), None)
    assert finding is not None


def test_bad_dockerfile_low_score():
    result = dockerfile_analyzer.analyze(BAD_DOCKERFILE)
    assert result.score < 50


def test_score_is_bounded():
    result = dockerfile_analyzer.analyze(BAD_DOCKERFILE)
    assert 0 <= result.score <= 100


def test_metadata_keys_present():
    result = dockerfile_analyzer.analyze(GOOD_DOCKERFILE)
    assert "instruction_count" in result.metadata
    assert "has_healthcheck" in result.metadata
    assert result.metadata["has_healthcheck"] is True


def test_multistage_from_counted():
    df = "FROM python:3.12-slim AS builder\nFROM python:3.12-slim\nUSER 1000\nHEALTHCHECK CMD true\n"
    result = dockerfile_analyzer.analyze(df)
    assert result.metadata["stage_count"] == 2


def test_scratch_base_not_flagged():
    df = 'FROM scratch\nCOPY binary /binary\nUSER 1000\nHEALTHCHECK CMD true\nCMD ["/binary"]\n'
    result = dockerfile_analyzer.analyze(df)
    assert not any(f.rule_id == "R001" for f in result.findings)


# ── R008: Single-stage build ──────────────────────────────────────────────────


def test_single_stage_flagged():
    df = "FROM python:3.12-slim\nUSER 1000\nHEALTHCHECK CMD true\n"
    result = dockerfile_analyzer.analyze(df)
    assert any(f.rule_id == "R008" for f in result.findings)


def test_multi_stage_not_flagged_r008():
    df = "FROM python:3.12-slim AS builder\nFROM python:3.12-slim\nUSER 1000\nHEALTHCHECK CMD true\n"
    result = dockerfile_analyzer.analyze(df)
    assert not any(f.rule_id == "R008" for f in result.findings)


def test_scratch_single_stage_not_flagged_r008():
    df = 'FROM scratch\nCOPY binary /binary\nUSER 1000\nHEALTHCHECK CMD true\nCMD ["/binary"]\n'
    result = dockerfile_analyzer.analyze(df)
    assert not any(f.rule_id == "R008" for f in result.findings)


def test_metadata_is_multi_stage():
    df = "FROM python:3.12-slim AS builder\nFROM python:3.12-slim\nUSER 1000\nHEALTHCHECK CMD true\n"
    result = dockerfile_analyzer.analyze(df)
    assert result.metadata["is_multi_stage"] is True


# ── R009: Non-minimal base image ──────────────────────────────────────────────


def test_non_minimal_base_flagged():
    df = "FROM ubuntu:22.04\nUSER 1000\nHEALTHCHECK CMD true\n"
    result = dockerfile_analyzer.analyze(df)
    assert any(f.rule_id == "R009" for f in result.findings)


def test_alpine_base_not_flagged_r009():
    df = "FROM python:3.12-alpine\nUSER 1000\nHEALTHCHECK CMD true\n"
    result = dockerfile_analyzer.analyze(df)
    assert not any(f.rule_id == "R009" for f in result.findings)


def test_slim_base_not_flagged_r009():
    df = "FROM python:3.12-slim\nUSER 1000\nHEALTHCHECK CMD true\n"
    result = dockerfile_analyzer.analyze(df)
    assert not any(f.rule_id == "R009" for f in result.findings)


def test_distroless_base_not_flagged_r009():
    df = "FROM gcr.io/distroless/python3:nonroot\nUSER 1000\nHEALTHCHECK CMD true\n"
    result = dockerfile_analyzer.analyze(df)
    assert not any(f.rule_id == "R009" for f in result.findings)


def test_metadata_has_minimal_base():
    df = "FROM python:3.12-slim\nUSER 1000\nHEALTHCHECK CMD true\n"
    result = dockerfile_analyzer.analyze(df)
    assert result.metadata["has_minimal_base"] is True


def test_metadata_not_minimal_base():
    df = "FROM ubuntu:22.04\nUSER 1000\nHEALTHCHECK CMD true\n"
    result = dockerfile_analyzer.analyze(df)
    assert result.metadata["has_minimal_base"] is False


# ── R010: Package cache cleanup ───────────────────────────────────────────────


def test_pip_no_cache_dir_flagged():
    df = "FROM python:3.12-slim\nRUN pip install requests\nUSER 1000\nHEALTHCHECK CMD true\n"
    result = dockerfile_analyzer.analyze(df)
    assert any(f.rule_id == "R010" for f in result.findings)


def test_pip_with_no_cache_dir_not_flagged():
    df = "FROM python:3.12-slim\nRUN pip install --no-cache-dir requests\nUSER 1000\nHEALTHCHECK CMD true\n"
    result = dockerfile_analyzer.analyze(df)
    assert not any(f.rule_id == "R010" for f in result.findings)


def test_apt_without_cleanup_flagged():
    df = "FROM ubuntu:22.04\nRUN apt-get install -y curl\nUSER 1000\nHEALTHCHECK CMD true\n"
    result = dockerfile_analyzer.analyze(df)
    assert any(f.rule_id == "R010" for f in result.findings)


def test_apt_with_cleanup_not_flagged():
    df = (
        "FROM ubuntu:22.04\n"
        "RUN apt-get install -y curl && rm -rf /var/lib/apt/lists/*\n"
        "USER 1000\nHEALTHCHECK CMD true\n"
    )
    result = dockerfile_analyzer.analyze(df)
    assert not any(f.rule_id == "R010" for f in result.findings)


def test_apk_without_no_cache_flagged():
    df = "FROM alpine:3.19\nRUN apk add curl\nUSER 1000\nHEALTHCHECK CMD true\n"
    result = dockerfile_analyzer.analyze(df)
    assert any(f.rule_id == "R010" for f in result.findings)


def test_apk_with_no_cache_not_flagged():
    df = "FROM alpine:3.19\nRUN apk add --no-cache curl\nUSER 1000\nHEALTHCHECK CMD true\n"
    result = dockerfile_analyzer.analyze(df)
    assert not any(f.rule_id == "R010" for f in result.findings)


def test_r010_deducts_once_for_multiple_pip_lines():
    df = (
        "FROM python:3.12-slim\n"
        "RUN pip install requests\n"
        "RUN pip install boto3\n"
        "USER 1000\nHEALTHCHECK CMD true\n"
    )
    result = dockerfile_analyzer.analyze(df)
    # Multiple findings but score should only lose 10 points for R010 (plus R007 for 2 RUNs, R008 for single-stage)
    r010_findings = [f for f in result.findings if f.rule_id == "R010"]
    assert len(r010_findings) == 2
    assert result.score == 100 - 10 - 5 - 10  # R010 once + R007 + R008


# ── R011: npm install instead of npm ci ──────────────────────────────────────


def test_npm_install_flagged():
    df = "FROM node:20-alpine\nRUN npm install\nUSER 1000\nHEALTHCHECK CMD true\n"
    result = dockerfile_analyzer.analyze(df)
    assert any(f.rule_id == "R011" for f in result.findings)


def test_npm_ci_not_flagged():
    df = "FROM node:20-alpine\nRUN npm ci\nUSER 1000\nHEALTHCHECK CMD true\n"
    result = dockerfile_analyzer.analyze(df)
    assert not any(f.rule_id == "R011" for f in result.findings)


def test_r011_deducts_once():
    df = (
        "FROM node:20-alpine\n"
        "RUN npm install\n"
        "RUN npm install --save-dev jest\n"
        "USER 1000\nHEALTHCHECK CMD true\n"
    )
    result = dockerfile_analyzer.analyze(df)
    r011_findings = [f for f in result.findings if f.rule_id == "R011"]
    assert len(r011_findings) == 2
    # Score: -5 (R011 once) -5 (R007 for 2 RUNs) -10 (R008 single-stage)
    assert result.score == 100 - 5 - 5 - 10
