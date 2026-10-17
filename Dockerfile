FROM node:22-bookworm-slim AS ui
WORKDIR /ui
COPY ui/package*.json ./
RUN npm ci --no-audit --no-fund
COPY ui/ ./
RUN npm run build

FROM python:3.12-slim-bookworm AS runtime
ENV PYTHONDONTWRITEBYTECODE=1 PYTHONUNBUFFERED=1 UV_COMPILE_BYTECODE=1 UV_LINK_MODE=copy PORT=8000
WORKDIR /app
RUN pip install --no-cache-dir uv==0.9.24 && groupadd --gid 10001 ringsight && useradd --uid 10001 --gid ringsight --create-home ringsight
COPY pyproject.toml uv.lock ./
RUN uv sync --frozen --no-dev
RUN mkdir -p /app/artifacts/private && chown ringsight:ringsight /app /app/artifacts /app/artifacts/private
COPY --chown=ringsight:ringsight server ./server
COPY --chown=ringsight:ringsight synth ./synth
COPY --chown=ringsight:ringsight seed ./seed
COPY --chown=ringsight:ringsight data ./data
COPY --from=ui --chown=ringsight:ringsight /ui/dist ./ui/dist
ENV PATH="/app/.venv/bin:$PATH"
USER ringsight
EXPOSE 8000
HEALTHCHECK --interval=30s --timeout=5s --start-period=15s --retries=3 CMD python -c "import urllib.request; urllib.request.urlopen('http://127.0.0.1:'+__import__('os').environ.get('PORT','8000')+'/live',timeout=4)"
CMD ["sh", "-c", "exec uvicorn server.app:app --host 0.0.0.0 --port ${PORT:-8000} --workers 1"]
