import os
from urllib.parse import quote_plus

_cached_url: str | None = None


def resolve_database_url() -> str:
    global _cached_url
    if _cached_url is not None:
        return _cached_url

    database_url = os.getenv("DATABASE_URL", "")
    if database_url:
        _cached_url = database_url
        return _cached_url

    user = os.getenv("POSTGRES_USER", "postgres")
    host = os.getenv("POSTGRES_HOST", "postgres")
    port = os.getenv("POSTGRES_PORT", "5432")
    db = os.getenv("APP_DB_NAME") or os.getenv("POSTGRES_DB", "mem0_app")

    from config.aws_secrets import fetch_rds_password

    password = fetch_rds_password()
    _cached_url = f"postgresql+psycopg://{quote_plus(user)}:{quote_plus(password)}@{host}:{port}/{db}"
    return _cached_url
