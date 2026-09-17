"""Launches Fargate scanner tasks directly from Lambda via ECS RunTask."""

import os

import boto3

ECS_CLUSTER = os.environ.get("ECS_CLUSTER_NAME", "")
TASK_DEFINITION = os.environ.get("ECS_TASK_DEFINITION", "")
SUBNETS = [s for s in os.environ.get("ECS_SUBNET_IDS", "").split(",") if s]
SECURITY_GROUP = os.environ.get("ECS_SECURITY_GROUP_ID", "")
# Must match whichever subnet type ECS_SUBNET_IDS actually holds -- private
# subnet tasks reach the internet via NAT Gateway (no public IP needed),
# public subnet tasks need one via IGW or they get zero egress.
ASSIGN_PUBLIC_IP = os.environ.get("ECS_ASSIGN_PUBLIC_IP", "DISABLED")

_ecs = None


def _client():
    global _ecs
    if _ecs is None:
        _ecs = boto3.client(
            "ecs", region_name=os.environ.get("AWS_DEFAULT_REGION", "us-east-1")
        )
    return _ecs


def launch_scan(scan_id: str, image_name: str, user_id: str) -> str:
    """Run a Fargate scanner task. Returns the ECS task ARN."""
    response = _client().run_task(
        cluster=ECS_CLUSTER,
        taskDefinition=TASK_DEFINITION,
        launchType="FARGATE",
        networkConfiguration={
            "awsvpcConfiguration": {
                "subnets": SUBNETS,
                "securityGroups": [SECURITY_GROUP],
                "assignPublicIp": ASSIGN_PUBLIC_IP,
            }
        },
        overrides={
            "containerOverrides": [
                {
                    "name": "scanner",
                    "environment": [
                        {"name": "SCAN_ID", "value": scan_id},
                        {"name": "IMAGE_NAME", "value": image_name},
                        {"name": "USER_ID", "value": user_id},
                    ],
                }
            ]
        },
    )
    tasks = response.get("tasks", [])
    if not tasks:
        failures = response.get("failures", [])
        reason = (
            failures[0].get("reason", "unknown") if failures else "no tasks launched"
        )
        raise RuntimeError(f"ECS RunTask failed: {reason}")
    return tasks[0]["taskArn"]
