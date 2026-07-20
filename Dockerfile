FROM node:22-alpine AS frontend-build

WORKDIR /build/frontend
RUN corepack enable
COPY frontend/package.json frontend/pnpm-lock.yaml frontend/pnpm-workspace.yaml ./
RUN pnpm install --frozen-lockfile
COPY frontend/ ./
RUN pnpm build


FROM python:3.12-slim AS runtime

ENV PYTHONDONTWRITEBYTECODE=1 \
    PYTHONUNBUFFERED=1 \
    PORT=7860 \
    FRONTEND_DIST_DIR=/app/frontend/dist

RUN useradd --create-home --uid 1000 appuser
WORKDIR /app/backend

COPY backend/requirements.txt ./requirements.txt
RUN pip install --no-cache-dir -r requirements.txt
COPY backend/app ./app
COPY --from=frontend-build /build/frontend/dist /app/frontend/dist

RUN chown -R appuser:appuser /app
USER appuser

EXPOSE 7860
CMD ["python", "-m", "app.run"]
