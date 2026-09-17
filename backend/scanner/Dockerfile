FROM aquasec/trivy:0.72.0 AS trivy-base
FROM anchore/syft:v1.46.0 AS syft-base

FROM python:3.12-slim

COPY --from=trivy-base /usr/local/bin/trivy /usr/local/bin/trivy
COPY --from=syft-base  /syft  /usr/local/bin/syft

WORKDIR /app

COPY requirements.txt .
RUN pip install --no-cache-dir -r requirements.txt

# Pre-download the trivy vulnerability DB so the container works in air-gapped
# private subnets (no NAT gateway, no internet egress).
# /var/cache/trivy is chmod 777 so the non-root scanner user can write the
# fanal/ analysis cache subdirectory at runtime.
ENV TRIVY_CACHE_DIR=/var/cache/trivy
RUN mkdir -p /var/cache/trivy && chmod 777 /var/cache/trivy && \
    trivy image --download-db-only --no-progress && \
    chmod -R a+rX /var/cache/trivy/db

COPY scan.py .

RUN adduser --disabled-password --gecos "" scanner
USER scanner

HEALTHCHECK --interval=30s --timeout=5s --retries=2 \
  CMD ["python", "-c", "import sys; sys.exit(0)"]

ENTRYPOINT ["python", "scan.py"]
