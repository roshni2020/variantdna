# One container: FastAPI on :8000 serving the API and the generated Nuxt app.
FROM node:22-slim AS web
WORKDIR /web
COPY apps/web/package.json apps/web/package-lock.json ./
RUN npm ci
COPY apps/web/ ./
RUN NUXT_PUBLIC_API_BASE= npx nuxt generate

FROM python:3.12-slim
COPY --from=ghcr.io/astral-sh/uv:0.8.15 /uv /usr/local/bin/uv
WORKDIR /app
COPY pyproject.toml uv.lock README.md ./
COPY packages/ packages/
RUN uv sync --frozen --no-dev --extra observability
COPY services/ services/
COPY --from=web /web/.output/public apps/web/.output/public
ENV VARIANTCOURT_DB=/data/variantcourt.db
VOLUME /data
EXPOSE 8000
CMD ["uv", "run", "--no-sync", "uvicorn", "services.api.main:app", "--host", "0.0.0.0", "--port", "8000"]
