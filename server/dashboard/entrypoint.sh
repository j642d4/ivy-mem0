#!/bin/sh
set -e

cd /app

ENVIRONMENT="${ENVIRONMENT:-staging}"
if [ "$ENVIRONMENT" = "production" ]; then
  SECRET_ID="/ivy/production/secret-manager-mem0"
else
  SECRET_ID="/ivy/staging/secret-manager-mem0"
fi

_secret=$(aws secretsmanager get-secret-value \
  --secret-id "$SECRET_ID" \
  --region "us-west-2" \
  --query SecretString \
  --output text)
eval "$(echo "$_secret" | node /home/nextjs/parse-secret.mjs)"

# Swap NEXT_PUBLIC_* placeholders baked into .next/ at build time with the
# real values fetched from Secrets Manager above. Each placeholder must be
# declared in the Dockerfile as `ENV NAME=NAME` so Next.js inlines the literal
# name. Currently: NEXT_PUBLIC_API_URL, NEXT_PUBLIC_INSTANCE_NAME
# New NEXT_PUBLIC_* vars must be added to the Dockerfile or this loop won't substitute them.
printenv | grep '^NEXT_PUBLIC_' | while IFS='=' read -r key value; do
  escaped=$(printf '%s' "$value" | sed -e 's/[\\&|]/\\&/g')
  find .next/ -type f -exec sed -i "s|$key|$escaped|g" {} \;
done

exec "$@"
