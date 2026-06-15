"""AWS Secrets Manager integration for all app configuration.

Two secrets are used:

1. AWS_APP_SECRET_ID  — flat JSON with all backend config (POSTGRES_USER,
   POSTGRES_HOST, POSTGRES_PORT, POSTGRES_DB, APP_DB_NAME, MILVUS_URL,
   MILVUS_TOKEN, JWT_SECRET, OPENAI_API_KEY, etc.).  Loaded into os.environ
   at startup so all existing os.getenv() calls work without modification.
   Does NOT contain the database password.

2. AWS_DB_SECRET_ID   — RDS-managed secret (standard AWS RDS rotation format).
   Contains the `password` field used to build the PostgreSQL connection URL.

ECS tasks authenticate via the task IAM role (boto3 default credential chain).
For local development, set these in .env to assume a role via STS:
  AWS_STAGING_ACCESS_KEY_ID
  AWS_STAGING_SECRET_ACCESS_KEY
  AWS_STAGING_STS_ROLE_ARN

Only one variable is needed in the ECS task definition:
  USE_AWS_SECRETS=true
"""

from __future__ import annotations

import json
import logging
import os

logger = logging.getLogger(__name__)

APP_SECRET_ID = "/ivy/staging/secret-manager-mem0"
DB_SECRET_ID  = "rds!db-d582e4ba-4786-41ba-b8f6-11b276c450b9"
AWS_REGION    = "us-west-2"


def _boto3_client(service: str):
    import boto3

    access_key = os.getenv("AWS_STAGING_ACCESS_KEY_ID", "")
    secret_key = os.getenv("AWS_STAGING_SECRET_ACCESS_KEY", "")
    role_arn = os.getenv("AWS_STAGING_STS_ROLE_ARN", "")

    if access_key and secret_key and role_arn:
        sts = boto3.client(
            "sts",
            region_name=AWS_REGION,
            aws_access_key_id=access_key,
            aws_secret_access_key=secret_key,
        )
        assumed = sts.assume_role(RoleArn=role_arn, RoleSessionName="mem0-server-local")
        creds = assumed["Credentials"]
        return boto3.client(
            service,
            region_name=AWS_REGION,
            aws_access_key_id=creds["AccessKeyId"],
            aws_secret_access_key=creds["SecretAccessKey"],
            aws_session_token=creds["SessionToken"],
        )

    return boto3.client(service, region_name=AWS_REGION)


def _fetch_secret(secret_id: str) -> dict:
    client = _boto3_client("secretsmanager")
    response = client.get_secret_value(SecretId=secret_id)
    return json.loads(response["SecretString"])


def load_secrets_to_environ() -> None:
    """Fetch Secret 1 (app config) and inject every key into os.environ.

    Called at the very top of main.py and alembic/env.py before any local
    module imports so module-level os.getenv() calls see the correct values.
    Does NOT include the database password — that is fetched separately from
    the RDS secret by fetch_rds_password().
    """
    secret = _fetch_secret(APP_SECRET_ID)

    for key, value in secret.items():
        if not os.environ.get(key):
            os.environ[key] = str(value)

    logger.info("Loaded %d keys from Secrets Manager into environment", len(secret))


def fetch_rds_password() -> str:
    """Fetch the database password from Secret 2 (RDS-managed secret).

    The RDS secret uses the standard AWS rotation format where the password
    is stored under the key `password`.
    """
    secret = _fetch_secret(DB_SECRET_ID)
    password = secret.get("password", "")
    if not password:
        raise ValueError(f"No 'password' key found in RDS secret: {secret_id}")

    return password
