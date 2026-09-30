# syntax=docker/dockerfile:1

FROM node:22-bookworm-slim AS frontend-build

ENV NEXT_TELEMETRY_DISABLED=1 \
    PECHE_TN_STATIC_EXPORT=1
WORKDIR /build

COPY package.json package-lock.json ./
RUN npm ci

COPY app ./app
COPY components ./components
COPY lib ./lib
COPY public ./public
COPY next.config.ts next-env.d.ts tsconfig.json ./

RUN npm run build:render \
    && test -s /build/out/index.html \
    && test -s /build/out/offline.html


FROM python:3.12-slim AS runtime

ENV PYTHONDONTWRITEBYTECODE=1 \
    PYTHONUNBUFFERED=1 \
    PIP_NO_CACHE_DIR=1 \
    PECHE_TN_STATIC_DIR=/app/web

WORKDIR /app
COPY pyproject.toml README.md ./
COPY apps/api ./apps/api
RUN pip install --no-cache-dir .

COPY deploy ./deploy
COPY --from=frontend-build /build/out ./web

USER 65532:65532
EXPOSE 10000

CMD ["sh", "-c", "exec uvicorn deploy.render_app:app --host 0.0.0.0 --port ${PORT:-10000} --proxy-headers --forwarded-allow-ips='*'"]
