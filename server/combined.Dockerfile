# ─── Stage 1: Build Next.js dashboard ────────────────────────────────────────
FROM node:22-alpine AS dashboard-builder
RUN apk add --no-cache libc6-compat
WORKDIR /dashboard

COPY server/dashboard/package.json server/dashboard/pnpm-lock.yaml* ./
RUN npm install -g pnpm@10 && pnpm i --frozen-lockfile

COPY server/dashboard/ .
ENV NEXT_TELEMETRY_DISABLED=1
ENV NEXT_PUBLIC_API_URL=NEXT_PUBLIC_API_URL
ENV NEXT_PUBLIC_INSTANCE_NAME=NEXT_PUBLIC_INSTANCE_NAME
RUN npm run build

# ─── Stage 2: Combined API + Dashboard ───────────────────────────────────────
FROM python:3.12

# Install Node.js 22
RUN curl -fsSL https://deb.nodesource.com/setup_22.x | bash - && \
    apt-get install -y nodejs && \
    apt-get clean && rm -rf /var/lib/apt/lists/*

# Install supervisord
RUN pip install supervisor

WORKDIR /app

# Python dependencies
COPY server/requirements.txt .
RUN pip install -r requirements.txt

# Install mem0 from local source (includes storage.py / main.py changes)
WORKDIR /app/packages
COPY pyproject.toml .
COPY poetry.lock .
COPY README.md .
COPY mem0 ./mem0
RUN pip install -e .[graph]

# Copy FastAPI server code
WORKDIR /app
COPY server/ .

# Copy built Next.js app from stage 1
COPY --from=dashboard-builder /dashboard/public ./dashboard/public
COPY --from=dashboard-builder /dashboard/.next/standalone ./dashboard/
COPY --from=dashboard-builder /dashboard/.next/static ./dashboard/.next/static
COPY server/dashboard/entrypoint.sh ./dashboard/entrypoint.sh
COPY server/dashboard-start.sh ./dashboard-start.sh
RUN chmod +x ./dashboard/entrypoint.sh ./dashboard-start.sh

# Supervisord config
COPY server/supervisord.conf /etc/supervisor/conf.d/supervisord.conf

EXPOSE 8000 3000

CMD ["/usr/local/bin/supervisord", "-c", "/etc/supervisor/conf.d/supervisord.conf"]
