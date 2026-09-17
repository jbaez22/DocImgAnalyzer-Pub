"""
ECS Fargate scanner entry point.
Reads SCAN_ID and IMAGE_NAME from env vars (injected by Lambda via ECS RunTask),
runs Trivy CVE scan + Syft SBOM generation, writes results to S3 and DynamoDB.
"""

import json
import os
import subprocess
import sys
from datetime import datetime, timezone

import boto3
from botocore.exceptions import ClientError

DYNAMODB_TABLE = os.environ["DYNAMODB_TABLE"]
REPORTS_BUCKET = os.environ["REPORTS_BUCKET"]
SBOM_BUCKET = os.environ["SBOM_BUCKET"]
AWS_REGION = os.environ.get("AWS_DEFAULT_REGION", "us-east-1")

_ddb = boto3.resource("dynamodb", region_name=AWS_REGION)
_s3 = boto3.client("s3", region_name=AWS_REGION)
_table = _ddb.Table(DYNAMODB_TABLE)


_RESERVED = {"error", "name", "status", "type", "value", "timestamp"}


def update_status(scan_id: str, status: str, **attrs) -> None:
    update_expr = "SET #s = :s, updated_at = :u"
    expr_names = {"#s": "status"}
    expr_values = {":s": status, ":u": datetime.now(timezone.utc).isoformat()}
    for k, v in attrs.items():
        if k in _RESERVED:
            placeholder = f"#attr_{k}"
            expr_names[placeholder] = k
            update_expr += f", {placeholder} = :{k}"
        else:
            update_expr += f", {k} = :{k}"
        expr_values[f":{k}"] = v
    kwargs: dict = {
        "Key": {"scan_id": scan_id},
        "UpdateExpression": update_expr,
        "ExpressionAttributeNames": expr_names,
        "ExpressionAttributeValues": expr_values,
    }
    # Don't overwrite a CANCELLED status with a terminal result
    if status in ("COMPLETE", "FAILED"):
        kwargs["ConditionExpression"] = "#s <> :cancelled"
        expr_values[":cancelled"] = "CANCELLED"
    try:
        _table.update_item(**kwargs)
    except ClientError as e:
        if e.response["Error"]["Code"] == "ConditionalCheckFailedException":
            print(
                f"[scan] {scan_id} already CANCELLED — skipping {status} update",
                flush=True,
            )
        else:
            raise


def run_trivy(image_name: str) -> dict:
    """Run trivy image scan and return parsed JSON output."""
    result = subprocess.run(
        ["trivy", "image", "--format", "json", "--skip-db-update", image_name],
        capture_output=True,
        text=True,
        timeout=480,
    )
    print(f"trivy returncode={result.returncode}", flush=True)
    if result.stderr:
        print(f"trivy stderr: {result.stderr[:2000]}", flush=True)
    if result.returncode not in (0, 1):
        raise RuntimeError(
            f"trivy failed (rc={result.returncode}): {result.stderr[:500]}"
        )
    if not result.stdout.strip():
        raise RuntimeError(
            f"trivy returned empty output (rc={result.returncode}): {result.stderr[:500]}"
        )
    return json.loads(result.stdout)


def _write_ecr_docker_config() -> None:
    """Write ECR credentials to ~/.docker/config.json so syft can pull ECR images."""
    ecr = boto3.client("ecr", region_name=AWS_REGION)
    auth_data = ecr.get_authorization_token()["authorizationData"][0]
    endpoint = auth_data["proxyEndpoint"]
    token = auth_data["authorizationToken"]
    config = {"auths": {endpoint: {"auth": token}}}
    docker_dir = os.path.expanduser("~/.docker")
    os.makedirs(docker_dir, exist_ok=True)
    with open(os.path.join(docker_dir, "config.json"), "w") as fh:
        json.dump(config, fh)


def run_syft(image_name: str) -> dict:
    """Run syft SBOM generation and return parsed CycloneDX JSON."""
    _write_ecr_docker_config()
    env = {**os.environ, "SYFT_CHECK_FOR_APP_UPDATE": "false"}
    result = subprocess.run(
        ["syft", f"registry:{image_name}", "-o", "cyclonedx-json"],
        capture_output=True,
        text=True,
        timeout=480,
        env=env,
    )
    if result.returncode != 0:
        raise RuntimeError(f"syft failed: {result.stderr}")
    if not result.stdout.strip():
        raise RuntimeError(f"syft returned empty output: {result.stderr[:500]}")
    return json.loads(result.stdout)


def count_cves(trivy_output: dict) -> dict:
    counts = {"CRITICAL": 0, "HIGH": 0, "MEDIUM": 0, "LOW": 0}
    for result in trivy_output.get("Results", []):
        for vuln in result.get("Vulnerabilities") or []:
            sev = vuln.get("Severity", "UNKNOWN").upper()
            if sev in counts:
                counts[sev] += 1
    return counts


def main() -> None:
    # Pipe-triggered rescans inject SQS_MESSAGE=<$.body>; Lambda-triggered scans
    # inject SCAN_ID and IMAGE_NAME directly as container override env vars.
    if os.environ.get("SQS_MESSAGE"):
        _body = json.loads(os.environ["SQS_MESSAGE"])
        scan_id = _body["scan_id"]
        image_name = _body["image_name"]
    else:
        scan_id = os.environ["SCAN_ID"]
        image_name = os.environ["IMAGE_NAME"]

    print(f"=== SCAN START | scan_id={scan_id} | image={image_name} ===", flush=True)

    record = _table.get_item(Key={"scan_id": scan_id}).get("Item", {})
    if record.get("status") == "CANCELLED":
        print(f"[scan] {scan_id} was cancelled before processing — exiting", flush=True)
        return

    update_status(scan_id, "PROCESSING")

    try:
        trivy_output = run_trivy(image_name)
        syft_output = run_syft(image_name)
        cve_counts = count_cves(trivy_output)

        ts = datetime.now(timezone.utc).strftime("%Y%m%dT%H%M%S")
        report_key = f"{scan_id}/{ts}-cve-report.json"
        sbom_key = f"{scan_id}/{ts}-sbom.json"

        _s3.put_object(
            Bucket=REPORTS_BUCKET,
            Key=report_key,
            Body=json.dumps(trivy_output),
            ContentType="application/json",
        )
        _s3.put_object(
            Bucket=SBOM_BUCKET,
            Key=sbom_key,
            Body=json.dumps(syft_output),
            ContentType="application/json",
        )

        update_status(
            scan_id,
            "COMPLETE",
            report_s3_key=report_key,
            sbom_s3_key=sbom_key,
            cve_critical=cve_counts["CRITICAL"],
            cve_high=cve_counts["HIGH"],
            cve_medium=cve_counts["MEDIUM"],
            cve_low=cve_counts["LOW"],
        )
        print(f"scan {scan_id} complete: {cve_counts}")

    except Exception as exc:
        update_status(scan_id, "FAILED", error=str(exc))
        print(f"scan {scan_id} failed: {exc}", file=sys.stderr)
        sys.exit(1)


if __name__ == "__main__":
    main()
