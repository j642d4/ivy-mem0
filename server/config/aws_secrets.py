import json
import logging
import os

logger = logging.getLogger(__name__)

ENVIRONMENT = os.getenv("ENVIRONMENT", "staging")

if ENVIRONMENT == "production":
    APP_SECRET_ID = "/ivy/production/secret-manager-mem0"
    DB_SECRET_ID = "rds!db-5ddce0ad-cf41-420b-8831-ae57888efebc"
else:
    APP_SECRET_ID = "/ivy/staging/secret-manager-mem0"
    DB_SECRET_ID = "rds!db-d582e4ba-4786-41ba-b8f6-11b276c450b9"

AWS_REGION = "us-west-2"


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
    secret = _fetch_secret(APP_SECRET_ID)
    loaded = 0
    for key, value in secret.items():
        if not os.environ.get(key):
            os.environ[key] = str(value)
            loaded += 1

    if not os.environ.get("POSTGRES_PASSWORD"):
        os.environ["POSTGRES_PASSWORD"] = fetch_rds_password()
        loaded += 1

    logger.info("Loaded %d keys from Secrets Manager into environment", loaded)


def fetch_rds_password() -> str:
    secret = _fetch_secret(DB_SECRET_ID)
    password = secret.get("password", "")
    if not password:
        raise ValueError(f"No 'password' key found in RDS secret: {DB_SECRET_ID}")
    return password
