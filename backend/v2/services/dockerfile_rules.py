"""
Phase 2 Dockerfile rule extensions — applied after the Phase 1 analyzer.

These rules are additive: they receive the AnalysisResult produced by
app.services.dockerfile_analyzer.analyze() and append new findings.

Rule IDs start at R012 to avoid collisions with the frozen Phase 1 set (R001–R011).
"""

import re

from app.models.schemas import Finding, Severity
from app.services.dockerfile_analyzer import AnalysisResult

# ── Patterns ──────────────────────────────────────────────────────────────────

# chmod 777 or variants that grant world-write: 777, a+w, o+w, a+rwx, etc.
# Used for detection (findings) — broad match.
_CHMOD_WORLD_WRITE = re.compile(
    r"\bchmod\b.*\b(777|[ao]\+[rwx]*w[rwx]*)\b",
    re.IGNORECASE,
)

# Used for substitution in the fixed dockerfile — matches the full chmod expression
# including optional flags (-R, -v, …) so re.sub() replaces only that expression
# and leaves the rest of the line (e.g. "npm ci &&") untouched.
_CHMOD_REPLACE = re.compile(
    r"\bchmod\s+(?:-\S+\s+)*(?:777|[ao]\+[rwx]*w[rwx]*)\s+\S+",
    re.IGNORECASE,
)

# Sensitive administrative ports: SSH(22), Telnet(23), RDP(3389)
_SENSITIVE_PORTS = {"22": "SSH", "23": "Telnet", "3389": "RDP"}


def _parse_instructions(content: str) -> list[tuple[str, str, int]]:
    """Parse Dockerfile into (INSTRUCTION, args, line_number) tuples."""
    instructions: list[tuple[str, str, int]] = []
    lines = content.splitlines()
    i = 0
    while i < len(lines):
        raw = lines[i].strip()
        if not raw or raw.startswith("#"):
            i += 1
            continue
        while raw.endswith("\\") and i + 1 < len(lines):
            raw = raw[:-1].rstrip() + " " + lines[i + 1].strip()
            i += 1
        parts = raw.split(None, 1)
        if parts:
            instructions.append(
                (parts[0].upper(), parts[1] if len(parts) > 1 else "", i + 1)
            )
        i += 1
    return instructions


def _apply_v2_fixes(dockerfile: str, fix_r012: bool, fix_r013: bool) -> str:
    """Rewrite a Dockerfile string applying v2 fixes and cleanup."""
    output = []
    for line in dockerfile.splitlines():
        stripped = line.strip()
        upper = stripped.upper()

        # Always: remove R004 comment lines Phase 1 emits for removed secrets.
        # These comments add noise — the ENV line is already gone.
        if stripped.startswith("# R004:"):
            continue

        # R012: replace chmod world-write with chown on ANY line (including
        # continuation lines that don't start with RUN).
        # re.sub() swaps only the chmod expression so the rest of the line
        # (e.g. "npm ci &&") is preserved.
        if fix_r012 and _CHMOD_WORLD_WRITE.search(stripped):
            leading = line[: len(line) - len(stripped)]  # preserve indentation
            replaced = _CHMOD_REPLACE.sub(
                "chown -R appuser:appuser <App_Path>", stripped
            )
            output.append(leading + replaced)
            continue

        # R013: drop sensitive EXPOSE lines entirely (or keep only safe ports)
        if fix_r013 and upper.startswith("EXPOSE "):
            tokens = stripped.split()[1:]  # everything after EXPOSE keyword
            safe = [t for t in tokens if t.split("/")[0] not in _SENSITIVE_PORTS]
            if not safe:
                continue  # entire EXPOSE line is sensitive — remove it
            output.append("EXPOSE " + " ".join(safe))
            continue

        output.append(line)

    return "\n".join(output)


def apply_v2_rules(result: AnalysisResult, content: str) -> AnalysisResult:
    """Augment result with Phase 2 rules. Mutates result in-place and returns it."""
    instructions = _parse_instructions(content)
    deductions = 0
    r012_triggered = False
    r013_triggered = False

    # ── R012: Overly permissive chmod ─────────────────────────────────────────
    for inst, args, line in instructions:
        if inst != "RUN":
            continue
        if _CHMOD_WORLD_WRITE.search(args):
            path_match = re.search(r"chmod\s+\S+\s+(\S+)", args)
            path = path_match.group(1) if path_match else "/app"
            result.findings.append(
                Finding(
                    rule_id="R012",
                    severity=Severity.warning,
                    title="Overly permissive chmod (world-writable)",
                    description=(
                        f"'chmod 777' (or equivalent) on '{path}' grants read, write, and execute "
                        "to every user in the container. Transfer ownership with chown so only "
                        "the application user can write."
                    ),
                    fix="RUN chown -R appuser:appuser <App_Path>",
                    line=line,
                )
            )
            deductions += 10
            r012_triggered = True

    # ── R013: Sensitive administrative port exposed ────────────────────────────
    for inst, args, line in instructions:
        if inst != "EXPOSE":
            continue
        for token in args.split():
            port = token.split("/")[0]  # strip /tcp or /udp suffix
            name = _SENSITIVE_PORTS.get(port)
            if name:
                result.findings.append(
                    Finding(
                        rule_id="R013",
                        severity=Severity.warning,
                        title=f"Sensitive port exposed ({name} port {port})",
                        description=(
                            f"EXPOSE {port} makes the {name} port reachable inside the "
                            "container network. Remove it unless your application genuinely "
                            "requires it — use 'docker exec' or ECS Exec for shell access instead."
                        ),
                        fix="# Use 'docker exec <container> /bin/sh' or ECS Exec for debugging.",
                        line=line,
                    )
                )
                deductions += 15
                r013_triggered = True

    result.score = max(0, result.score - deductions)

    # Post-process the fixed Dockerfile through v2 fixes.
    # Run whenever Phase 1 produced a fixed_dockerfile (R004 comment cleanup
    # is always needed). If Phase 1 had no findings but v2 rules fired, start
    # from the original content so a corrected output is still produced.
    if result.fixed_dockerfile:
        result.fixed_dockerfile = _apply_v2_fixes(
            result.fixed_dockerfile, r012_triggered, r013_triggered
        )
    elif r012_triggered or r013_triggered:
        result.fixed_dockerfile = _apply_v2_fixes(
            content, r012_triggered, r013_triggered
        )

    return result
