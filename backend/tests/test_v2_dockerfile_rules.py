from app.services.dockerfile_analyzer import AnalysisResult, analyze
from v2.services.dockerfile_rules import apply_v2_rules


def _run(content: str) -> AnalysisResult:
    result = analyze(content)
    return apply_v2_rules(result, content)


# ── R012: chmod 777 ───────────────────────────────────────────────────────────

CHMOD_777 = """\
FROM python:3.12-slim
RUN chmod 777 /app
USER 1000
HEALTHCHECK CMD echo ok
CMD ["python", "app.py"]
"""

CHMOD_CLEAN = """\
FROM python:3.12-slim
RUN chown -R appuser:appuser /app
USER 1000
HEALTHCHECK CMD echo ok
CMD ["python", "app.py"]
"""


def test_chmod_777_detected():
    result = _run(CHMOD_777)
    assert any(f.rule_id == "R012" for f in result.findings)


def test_chmod_777_score_reduced():
    clean = _run(CHMOD_CLEAN)
    bad = _run(CHMOD_777)
    assert bad.score < clean.score


def test_chmod_clean_no_r012():
    result = _run(CHMOD_CLEAN)
    assert not any(f.rule_id == "R012" for f in result.findings)


def test_chmod_777_fix_uses_placeholder():
    result = _run(CHMOD_777)
    finding = next(f for f in result.findings if f.rule_id == "R012")
    assert finding.fix == "RUN chown -R appuser:appuser <App_Path>"


def test_chmod_777_fixed_dockerfile_uses_chown():
    result = _run(CHMOD_777)
    assert result.fixed_dockerfile is not None
    assert "chown -R appuser:appuser <App_Path>" in result.fixed_dockerfile
    assert "chmod 777" not in result.fixed_dockerfile


def test_chmod_recursive_fixed_dockerfile_uses_placeholder():
    # chmod -R 777 /app — regex must not capture "777" as the path
    content = """\
FROM python:3.12-slim
RUN chmod -R 777 /app
USER 1000
HEALTHCHECK CMD echo ok
CMD ["python", "app.py"]
"""
    result = _run(content)
    assert result.fixed_dockerfile is not None
    assert "chown -R appuser:appuser <App_Path>" in result.fixed_dockerfile
    assert "777" not in result.fixed_dockerfile


def test_chmod_on_continuation_line_is_replaced():
    # R007 consolidates two RUN statements; chmod ends up on a continuation line
    content = """\
FROM python:3.12-slim
RUN npm install
RUN chmod 777 /app
USER 1000
HEALTHCHECK CMD echo ok
CMD ["python", "app.py"]
"""
    result = _run(content)
    assert result.fixed_dockerfile is not None
    assert "chmod 777" not in result.fixed_dockerfile
    assert "chown -R appuser:appuser <App_Path>" in result.fixed_dockerfile


def test_chmod_on_same_line_as_other_command():
    # chmod appears after && in a single RUN — only chmod part should be replaced
    content = """\
FROM python:3.12-slim
RUN pip install --no-cache-dir -r requirements.txt && chmod 777 /app
USER 1000
HEALTHCHECK CMD echo ok
CMD ["python", "app.py"]
"""
    result = _run(content)
    assert result.fixed_dockerfile is not None
    assert "chmod 777" not in result.fixed_dockerfile
    assert "chown -R appuser:appuser <App_Path>" in result.fixed_dockerfile
    # The pip install part must survive
    assert "pip install" in result.fixed_dockerfile


def test_r004_comments_stripped_from_fixed_dockerfile():
    # Phase 1 emits "# R004: '...' removed — ..." lines; v2 must remove them
    content = """\
FROM python:3.12-slim
ENV AWS_SECRET_ACCESS_KEY=supersecret
USER 1000
HEALTHCHECK CMD echo ok
CMD ["python", "app.py"]
"""
    result = _run(content)
    assert result.fixed_dockerfile is not None
    assert "# R004:" not in result.fixed_dockerfile
    assert "AWS_SECRET_ACCESS_KEY" not in result.fixed_dockerfile


# ── R013: sensitive port ───────────────────────────────────────────────────────

EXPOSE_SSH = """\
FROM python:3.12-slim
EXPOSE 22
USER 1000
HEALTHCHECK CMD echo ok
CMD ["python", "app.py"]
"""

EXPOSE_SAFE = """\
FROM python:3.12-slim
EXPOSE 8080
USER 1000
HEALTHCHECK CMD echo ok
CMD ["python", "app.py"]
"""

EXPOSE_RDP = """\
FROM python:3.12-slim
EXPOSE 3389/tcp
USER 1000
HEALTHCHECK CMD echo ok
CMD ["python", "app.py"]
"""

EXPOSE_MIXED = """\
FROM python:3.12-slim
EXPOSE 8080 22
USER 1000
HEALTHCHECK CMD echo ok
CMD ["python", "app.py"]
"""


def test_expose_ssh_detected():
    result = _run(EXPOSE_SSH)
    assert any(f.rule_id == "R013" for f in result.findings)


def test_expose_ssh_score_reduced():
    clean = _run(EXPOSE_SAFE)
    bad = _run(EXPOSE_SSH)
    assert bad.score < clean.score


def test_expose_safe_port_no_r013():
    result = _run(EXPOSE_SAFE)
    assert not any(f.rule_id == "R013" for f in result.findings)


def test_expose_rdp_with_protocol_suffix():
    result = _run(EXPOSE_RDP)
    assert any(f.rule_id == "R013" for f in result.findings)


def test_expose_ssh_fix_no_remove_line():
    result = _run(EXPOSE_SSH)
    finding = next(f for f in result.findings if f.rule_id == "R013")
    assert finding.fix is not None
    assert "Remove" not in finding.fix
    assert "EXPOSE 22" not in finding.fix


def test_expose_ssh_fix_mentions_exec():
    result = _run(EXPOSE_SSH)
    finding = next(f for f in result.findings if f.rule_id == "R013")
    assert "exec" in finding.fix.lower()


def test_expose_ssh_removed_from_fixed_dockerfile():
    result = _run(EXPOSE_SSH)
    assert result.fixed_dockerfile is not None
    assert "EXPOSE 22" not in result.fixed_dockerfile


def test_expose_mixed_keeps_safe_port():
    result = _run(EXPOSE_MIXED)
    assert result.fixed_dockerfile is not None
    assert "EXPOSE 8080" in result.fixed_dockerfile
    assert "22" not in result.fixed_dockerfile
