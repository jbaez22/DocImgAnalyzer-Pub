import re
from dataclasses import dataclass, field

from app.models.schemas import Finding, Severity

# Env/arg key names that suggest a secret value.
# No \b boundaries — underscore is \w so \b fails on DB_PASSWORD, API_TOKEN, etc.
# Substring match is intentional: any key containing these words is a candidate.
_SECRET_PATTERN = re.compile(
    r"(password|passwd|pwd|secret|token|api_key|apikey|credential|private_key|access_key)",
    re.IGNORECASE,
)

# curl/wget piped directly to a shell
_PIPE_INSTALL_PATTERN = re.compile(r"(curl|wget).+\|\s*(ba)?sh", re.IGNORECASE)

# Package manager patterns for R010
_APT_INSTALL_PATTERN = re.compile(r"apt-get\s+install", re.IGNORECASE)
_APT_CLEANUP_PATTERN = re.compile(r"rm\s+-rf\s+/var/lib/apt/lists", re.IGNORECASE)
_PIP_INSTALL_PATTERN = re.compile(r"pip\d*\s+install", re.IGNORECASE)
_PIP_NO_CACHE_PATTERN = re.compile(r"--no-cache-dir", re.IGNORECASE)
_APK_ADD_PATTERN = re.compile(r"apk\s+add", re.IGNORECASE)
_APK_NO_CACHE_PATTERN = re.compile(r"--no-cache(?!-)", re.IGNORECASE)

# npm install without lock-file for R011
_NPM_INSTALL_PATTERN = re.compile(r"\bnpm\s+install\b", re.IGNORECASE)
_NPM_CI_PATTERN = re.compile(r"\bnpm\s+ci\b", re.IGNORECASE)

# Minimal base image keywords for R009
_MINIMAL_BASE_KEYWORDS = frozenset(
    ["alpine", "slim", "distroless", "chainguard", "busybox"]
)


@dataclass
class AnalysisResult:
    score: int = 100
    findings: list[Finding] = field(default_factory=list)
    fixed_dockerfile: str | None = None
    metadata: dict = field(default_factory=dict)


def _parse_instructions(content: str) -> list[tuple[str, str, int]]:
    """
    Parse Dockerfile content into a list of (instruction, arguments, line_number).
    Handles line continuations (trailing backslash) and skips comments.
    """
    instructions: list[tuple[str, str, int]] = []
    lines = content.splitlines()
    i = 0
    while i < len(lines):
        raw = lines[i].strip()
        if not raw or raw.startswith("#"):
            i += 1
            continue
        # Merge continuation lines
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


def _is_minimal_base(image_ref: str) -> bool:
    """Return True if the image ref points to a known minimal base image."""
    if image_ref.lower() == "scratch":
        return True
    lower = image_ref.lower()
    return any(kw in lower for kw in _MINIMAL_BASE_KEYWORDS)


def analyze(content: str) -> AnalysisResult:
    result = AnalysisResult()
    instructions = _parse_instructions(content)
    names = [inst for inst, _, _ in instructions]
    deductions = 0

    from_instructions = [
        (args, line) for inst, args, line in instructions if inst == "FROM"
    ]
    stage_count = len(from_instructions)

    # ── R001: Unpinned base image ──────────────────────────────────────────────
    for inst, args, line in instructions:
        if inst != "FROM":
            continue
        image_ref = args.split()[0]
        if image_ref.lower() == "scratch":
            continue
        if ":" not in image_ref or image_ref.endswith(":latest"):
            base = image_ref.split(":")[0]
            result.findings.append(
                Finding(
                    rule_id="R001",
                    severity=Severity.error,
                    title="Unpinned base image",
                    description=(
                        f"'{image_ref}' uses ':latest' or has no tag. "
                        "Pin to a specific version or digest for reproducible builds."
                    ),
                    fix=f"FROM {base}:<specific-version>",
                    line=line,
                )
            )
            deductions += 20

    # ── R002: No USER or explicit root USER ────────────────────────────────────
    user_instructions = [
        (args.strip(), line) for inst, args, line in instructions if inst == "USER"
    ]
    if not user_instructions:
        result.findings.append(
            Finding(
                rule_id="R002",
                severity=Severity.error,
                title="No USER instruction — container runs as root",
                description="Add a non-root USER to limit the blast radius of a container escape.",
                fix="USER 1000",
            )
        )
        deductions += 25
    else:
        for user_val, line in user_instructions:
            if user_val in ("root", "0"):
                result.findings.append(
                    Finding(
                        rule_id="R002",
                        severity=Severity.error,
                        title="Container explicitly runs as root",
                        description=f"USER is set to '{user_val}'. Switch to a non-root user.",
                        fix="USER 1000",
                        line=line,
                    )
                )
                deductions += 25

    # ── R003: No HEALTHCHECK ───────────────────────────────────────────────────
    if "HEALTHCHECK" not in names:
        result.findings.append(
            Finding(
                rule_id="R003",
                severity=Severity.warning,
                title="No HEALTHCHECK instruction",
                description="Add a HEALTHCHECK so orchestrators can detect and restart unhealthy containers.",
                fix="HEALTHCHECK --interval=30s --timeout=5s --retries=3 \\\n    CMD curl -f http://localhost:8080/health || exit 1",
            )
        )
        deductions += 10

    # ── R004: Secret-like key in ENV or ARG ───────────────────────────────────
    for inst, args, line in instructions:
        if inst not in ("ENV", "ARG"):
            continue
        key = args.split("=")[0].strip().split()[0]
        if _SECRET_PATTERN.search(key):
            result.findings.append(
                Finding(
                    rule_id="R004",
                    severity=Severity.error,
                    title="Possible secret in ENV/ARG",
                    description=(
                        f"'{key}' looks like a secret. "
                        "Use AWS Secrets Manager or Docker build secrets (--secret) instead."
                    ),
                    fix=(
                        f"# Remove '{key}' from ENV/ARG — never store secrets in image layers.\n"
                        "# Use Docker BuildKit secrets instead:\n"
                        "#\n"
                        "#   # syntax=docker/dockerfile:1\n"
                        "#\n"
                        f"#   RUN --mount=type=secret,id={key.lower()} \\\n"
                        f"#       export {key}=$(cat /run/secrets/{key.lower()}) && \\\n"
                        "#       <your command here>\n"
                        "#\n"
                        "# Then build with:  docker build --secret id="
                        f"{key.lower()},src=.env .\n"
                        "# Or inject at runtime via AWS Secrets Manager / Parameter Store."
                    ),
                    line=line,
                )
            )
            deductions += 30

    # ── R005: curl/wget piped to shell ────────────────────────────────────────
    for inst, args, line in instructions:
        if inst == "RUN" and _PIPE_INSTALL_PATTERN.search(args):
            result.findings.append(
                Finding(
                    rule_id="R005",
                    severity=Severity.error,
                    title="Piped install script",
                    description=(
                        "Piping curl/wget directly to a shell is a supply-chain risk. "
                        "Download the script, verify its checksum, then execute."
                    ),
                    fix="RUN curl -fsSL https://example.com/install.sh -o install.sh \\\n    && echo '<expected-sha256>  install.sh' | sha256sum -c \\\n    && bash install.sh \\\n    && rm install.sh",
                    line=line,
                )
            )
            deductions += 20

    # ── R006: ADD instead of COPY for local files ─────────────────────────────
    for inst, args, line in instructions:
        if inst == "ADD" and not re.search(r"https?://", args):
            result.findings.append(
                Finding(
                    rule_id="R006",
                    severity=Severity.warning,
                    title="ADD used instead of COPY",
                    description=(
                        "Prefer COPY for local files. "
                        "ADD has implicit tar-extraction and URL-fetch behaviour that can be surprising."
                    ),
                    fix=f"COPY {args}",
                    line=line,
                )
            )
            deductions += 5

    # ── R007: Many separate RUN instructions ──────────────────────────────────
    run_count = names.count("RUN")
    if run_count > 1:
        result.findings.append(
            Finding(
                rule_id="R007",
                severity=Severity.warning,
                title="Multiple RUN instructions create unnecessary layers",
                description=(
                    f"Found {run_count} RUN instructions. "
                    "Chain related commands with '&&' to reduce layer count and image size."
                ),
                fix="RUN command1 \\\n    && command2 \\\n    && command3",
            )
        )
        deductions += 5

    # ── R008: Single-stage build ───────────────────────────────────────────────
    if stage_count == 1:
        single_base = from_instructions[0][0].split()[0] if from_instructions else ""
        if single_base.lower() != "scratch":
            result.findings.append(
                Finding(
                    rule_id="R008",
                    severity=Severity.warning,
                    title="Single-stage build — consider multi-stage",
                    description=(
                        "A single-stage build ships build tools, caches, and intermediate files into the "
                        "final image. Use a builder stage to compile/install and copy only the artifacts "
                        "into a minimal runtime stage."
                    ),
                    fix=(
                        "FROM <build-image> AS builder\n"
                        "# ... build steps ...\n\n"
                        "FROM <minimal-runtime-image>\n"
                        "COPY --from=builder /app /app"
                    ),
                    line=from_instructions[0][1] if from_instructions else None,
                )
            )
            deductions += 10

    # ── R009: Non-minimal base image (final stage) ────────────────────────────
    if from_instructions:
        final_ref = from_instructions[-1][0].split()[0]  # last FROM, strip AS alias
        _, _, final_line = [t for t in instructions if t[0] == "FROM"][-1]
        if final_ref.lower() != "scratch" and not _is_minimal_base(final_ref):
            result.findings.append(
                Finding(
                    rule_id="R009",
                    severity=Severity.warning,
                    title="Non-minimal base image",
                    description=(
                        f"'{final_ref}' is not a minimal base image. "
                        "Prefer Alpine, slim, distroless, or Chainguard variants to reduce attack surface and image size."
                    ),
                    fix=f"FROM {final_ref.split(':')[0]}:<version>-alpine  # or -slim / distroless equivalent",
                    line=final_line,
                )
            )
            deductions += 10

    # ── R010: Package cache not cleaned up ────────────────────────────────────
    pkg_cache_deducted = False
    for inst, args, line in instructions:
        if inst != "RUN":
            continue
        if _APT_INSTALL_PATTERN.search(args) and not _APT_CLEANUP_PATTERN.search(args):
            result.findings.append(
                Finding(
                    rule_id="R010",
                    severity=Severity.warning,
                    title="apt-get cache not cleaned",
                    description=(
                        "apt-get install without 'rm -rf /var/lib/apt/lists/*' leaves package index files "
                        "in the image layer, increasing image size."
                    ),
                    fix="RUN apt-get update \\\n    && apt-get install -y --no-install-recommends <pkgs> \\\n    && rm -rf /var/lib/apt/lists/*",
                    line=line,
                )
            )
            if not pkg_cache_deducted:
                deductions += 10
                pkg_cache_deducted = True
        if _PIP_INSTALL_PATTERN.search(args) and not _PIP_NO_CACHE_PATTERN.search(args):
            result.findings.append(
                Finding(
                    rule_id="R010",
                    severity=Severity.warning,
                    title="pip install without --no-cache-dir",
                    description=(
                        "pip caches downloaded packages inside the image layer. "
                        "Use --no-cache-dir to keep the image smaller."
                    ),
                    fix=re.sub(
                        r"(pip\d*\s+install)\b",
                        r"\1 --no-cache-dir",
                        args,
                        flags=re.IGNORECASE,
                    ),
                    line=line,
                )
            )
            if not pkg_cache_deducted:
                deductions += 10
                pkg_cache_deducted = True
        if _APK_ADD_PATTERN.search(args) and not _APK_NO_CACHE_PATTERN.search(args):
            result.findings.append(
                Finding(
                    rule_id="R010",
                    severity=Severity.warning,
                    title="apk add without --no-cache",
                    description=(
                        "apk add without --no-cache writes the package index to the image layer. "
                        "Use --no-cache to skip the index cache."
                    ),
                    fix=re.sub(
                        r"(apk\s+add)\b", r"\1 --no-cache", args, flags=re.IGNORECASE
                    ),
                    line=line,
                )
            )
            if not pkg_cache_deducted:
                deductions += 10
                pkg_cache_deducted = True

    # ── R011: npm install instead of npm ci ───────────────────────────────────
    npm_ci_deducted = False
    for inst, args, line in instructions:
        if inst != "RUN":
            continue
        if _NPM_INSTALL_PATTERN.search(args) and not _NPM_CI_PATTERN.search(args):
            result.findings.append(
                Finding(
                    rule_id="R011",
                    severity=Severity.warning,
                    title="npm install instead of npm ci",
                    description=(
                        "npm install can silently update package-lock.json and install versions "
                        "outside the pinned range. Use npm ci for reproducible, lock-file-enforced installs."
                    ),
                    fix=re.sub(
                        r"\bnpm\s+install\b", "npm ci", args, flags=re.IGNORECASE
                    ),
                    line=line,
                )
            )
            if not npm_ci_deducted:
                deductions += 5
                npm_ci_deducted = True

    result.score = max(0, 100 - deductions)

    final_base_ref = from_instructions[-1][0].split()[0] if from_instructions else ""
    result.metadata = {
        "instruction_count": len(instructions),
        "stage_count": stage_count,
        "has_healthcheck": "HEALTHCHECK" in names,
        "has_non_root_user": bool(user_instructions)
        and all(u not in ("root", "0") for u, _ in user_instructions),
        "is_multi_stage": stage_count >= 2,
        "has_minimal_base": _is_minimal_base(final_base_ref)
        if final_base_ref
        else True,
    }

    if result.findings:
        result.fixed_dockerfile = _generate_fixed_dockerfile(content, result.findings)

    return result


def _generate_fixed_dockerfile(content: str, findings: list[Finding]) -> str:
    """
    Apply best-effort automatic fixes to the original Dockerfile content.

    Pass 1 — line-level fixes:  R001, R004, R005, R006, R010, R011
    Pass 2 — structural fix:    R007 (consolidate consecutive RUN instructions)
    Pass 3 — injection fixes:   R002, R003 (insert USER / HEALTHCHECK)
    Preamble — header comments: R008, R009 (suggest multi-stage / minimal base)
    """
    rule_ids = {f.rule_id for f in findings}

    # ── Pass 1: line-level fixes ───────────────────────────────────────────────
    pass1: list[str] = []
    for line in content.splitlines():
        stripped = line.strip()
        upper = stripped.upper()

        # R001 — pin unpinned FROM tag
        if "R001" in rule_ids and upper.startswith("FROM "):
            parts = stripped.split()
            if len(parts) >= 2:
                image_ref = parts[1]
                if image_ref.lower() != "scratch" and (
                    ":" not in image_ref or image_ref.endswith(":latest")
                ):
                    base = image_ref.split(":")[0]
                    rest = " ".join(parts[2:])
                    fixed = f"FROM {base}:<specific-version>" + (
                        f" {rest}" if rest else ""
                    )
                    pass1.append(
                        f"{fixed}  # R001 fix: pin to a specific version tag or digest"
                    )
                    continue

        # R004 — remove secret ENV/ARG lines entirely (value must never appear in output)
        if "R004" in rule_ids and upper.startswith(("ENV ", "ARG ")):
            key = stripped.split(None, 1)[1].split("=")[0].strip().split()[0]
            if _SECRET_PATTERN.search(key):
                pass1.append(
                    f"# R004: '{key}' removed — use BuildKit --mount=type=secret or AWS Secrets Manager"
                )
                continue

        # R006 — replace ADD with COPY for local files
        if "R006" in rule_ids and upper.startswith("ADD "):
            args = stripped[4:]
            if not re.search(r"https?://", args):
                pass1.append(f"COPY {args}  # R006 fix: use COPY instead of ADD")
                continue

        # R005 — replace unsafe pipe-install with checksum-verified template
        if (
            "R005" in rule_ids
            and upper.startswith("RUN ")
            and _PIPE_INSTALL_PATTERN.search(stripped)
        ):
            pass1.append("# R005 fix: download script, verify checksum, then execute")
            pass1.append("# RUN curl -fsSL <url> -o install.sh \\")
            pass1.append("#     && echo '<sha256>  install.sh' | sha256sum -c \\")
            pass1.append("#     && bash install.sh && rm install.sh")
            pass1.append(f"# Original (unsafe): {line}")
            continue

        # R010 + R011 — package cache cleanup and npm ci (applied together)
        if upper.startswith("RUN ") and not stripped.startswith("#"):
            modified = line
            apt_comment = False

            if "R010" in rule_ids:
                if _PIP_INSTALL_PATTERN.search(
                    modified
                ) and not _PIP_NO_CACHE_PATTERN.search(modified):
                    modified = re.sub(
                        r"(pip\d*\s+install)\b",
                        r"\1 --no-cache-dir",
                        modified,
                        flags=re.IGNORECASE,
                    )
                if _APK_ADD_PATTERN.search(
                    modified
                ) and not _APK_NO_CACHE_PATTERN.search(modified):
                    modified = re.sub(
                        r"(apk\s+add)\b",
                        r"\1 --no-cache",
                        modified,
                        flags=re.IGNORECASE,
                    )
                if _APT_INSTALL_PATTERN.search(
                    line
                ) and not _APT_CLEANUP_PATTERN.search(line):
                    apt_comment = True

            if "R011" in rule_ids:
                if _NPM_INSTALL_PATTERN.search(modified) and not _NPM_CI_PATTERN.search(
                    modified
                ):
                    modified = re.sub(
                        r"\bnpm\s+install\b", "npm ci", modified, flags=re.IGNORECASE
                    )

            if apt_comment:
                pass1.append(
                    "# R010 fix: append '&& rm -rf /var/lib/apt/lists/*' to clean apt cache"
                )

            if modified != line:
                pass1.append(f"{modified}  # R010/R011 fix")
                continue

        pass1.append(line)

    # ── Pass 2: consolidate consecutive RUN instructions (R007) ───────────────
    pass2: list[str]
    if "R007" not in rule_ids:
        pass2 = pass1
    else:
        pass2 = []
        run_buffer: list[str] = []  # physical lines belonging to current RUN group
        in_continuation = False  # True while inside a multi-line RUN (trailing \)

        def _flush_runs() -> None:
            if not run_buffer:
                return
            if len(run_buffer) == 1:
                pass2.append(run_buffer[0])
            else:
                # Extract each command, stripping 'RUN ' prefix and inline continuations
                cmds: list[str] = []
                for rline in run_buffer:
                    cmd = re.sub(r"^RUN\s+", "", rline.strip(), flags=re.IGNORECASE)
                    # Collapse any existing inline && continuation whitespace
                    cmd = re.sub(r"\s*\\\s*$", "", cmd).strip()
                    cmds.append(cmd)
                pass2.append("RUN " + " && \\\n    ".join(cmds))
            run_buffer.clear()

        for line in pass1:
            stripped = line.strip()
            upper = stripped.upper()

            if in_continuation:
                # Append this physical continuation line to the last buffered RUN
                run_buffer[-1] = run_buffer[-1] + "\n" + line
                if not stripped.endswith("\\"):
                    in_continuation = False
            elif upper.startswith("RUN ") and not stripped.startswith("#"):
                run_buffer.append(line)
                in_continuation = stripped.endswith("\\")
            else:
                _flush_runs()
                pass2.append(line)

        _flush_runs()

    # ── Pass 3: inject USER (R002) and HEALTHCHECK (R003) ─────────────────────
    user_injected = "R002" not in rule_ids
    health_injected = "R003" not in rule_ids
    output: list[str] = []

    for line in pass2:
        stripped = line.strip()
        upper = stripped.upper()

        if upper.startswith(("CMD ", "CMD[", "ENTRYPOINT ", "ENTRYPOINT[")):
            if not health_injected:
                output.append("HEALTHCHECK --interval=30s --timeout=5s --retries=3 \\")
                output.append("    CMD curl -f http://localhost:8080/health || exit 1")
                health_injected = True
            if not user_injected:
                output.append("USER 1000")
                user_injected = True

        output.append(line)

    # If no CMD/ENTRYPOINT was found, append at the end
    if not health_injected:
        output.append("HEALTHCHECK --interval=30s --timeout=5s --retries=3 \\")
        output.append("    CMD curl -f http://localhost:8080/health || exit 1")
    if not user_injected:
        output.append("USER 1000")

    # ── Preamble: structural suggestions (R008, R009) ─────────────────────────
    preamble: list[str] = []
    if "R008" in rule_ids:
        preamble.append(
            "# R008 fix: split into builder + runtime stages to reduce final image size"
        )
        preamble.append("# Example structure:")
        preamble.append("# FROM <build-image> AS builder")
        preamble.append("# ... install build deps, compile ...")
        preamble.append("# FROM <minimal-runtime-image>")
        preamble.append("# COPY --from=builder /app /app")
    if "R009" in rule_ids:
        preamble.append("# R009 fix: switch to a minimal base image variant, e.g.:")
        preamble.append("# python -> python:<version>-slim or python:<version>-alpine")
        preamble.append("# node   -> node:<version>-alpine")
        preamble.append(
            "# ubuntu -> gcr.io/distroless/base or cgr.dev/chainguard/static"
        )

    if preamble:
        return "\n".join(preamble) + "\n\n" + "\n".join(output)

    return "\n".join(output)
