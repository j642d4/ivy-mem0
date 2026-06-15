#!/bin/sh
set -e

cd /app

# ── AWS Secrets Manager ───────────────────────────────────────────────────────
# Fetch all frontend config from Secrets Manager into the process environment.
# Only AWS_APP_SECRET_ID (and optionally AWS_SECRETS_REGION) need to be set
# in the ECS task definition — everything else comes from the secret, including
# NEXT_PUBLIC_API_URL, NEXT_PUBLIC_INSTANCE_NAME, and API_INTERNAL_URL.
if [ -n "$AWS_APP_SECRET_ID" ]; then
  _secret=$(aws secretsmanager get-secret-value \
    --secret-id "$AWS_APP_SECRET_ID" \
    --region "${AWS_SECRETS_REGION:-us-west-2}" \
    --query SecretString \
    --output text)
  eval "$(echo "$_secret" | node /home/nextjs/parse-secret.mjs)"
fi
# ─────────────────────────────────────────────────────────────────────────────

# Swap NEXT_PUBLIC_* placeholders baked into .next/ at build time with the
# real values now present in the environment (either from Secrets Manager above
# or passed directly via the task definition).
printenv | grep '^NEXT_PUBLIC_' | while IFS='=' read -r key value; do
  escaped=$(printf '%s' "$value" | sed -e 's/[\\&|]/\\&/g')
  find .next/ -type f -exec sed -i "s|$key|$escaped|g" {} \;
done

exec "$@"
