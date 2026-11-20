FROM python:3.11-slim AS builder

WORKDIR /build
RUN pip install --no-cache-dir --upgrade pip build
COPY services/control-plane/pyproject.toml /build/pyproject.toml
COPY services/control-plane/src /build/src
RUN pip wheel --no-cache-dir --wheel-dir /wheels /build

FROM python:3.11-slim AS runtime

RUN groupadd --gid 10001 aegis && \
    useradd --uid 10001 --gid aegis --shell /usr/sbin/nologin --create-home aegis

WORKDIR /app
COPY --from=builder /wheels /wheels
RUN pip install --no-cache-dir /wheels/*.whl && rm -rf /wheels

COPY policies /app/policies
COPY infra /app/infra
COPY deploy /app/deploy
COPY contracts /app/contracts

RUN chown -R aegis:aegis /app
USER 10001:10001

EXPOSE 8080
ENV AEGIS_API_HOST=0.0.0.0 \
    AEGIS_API_PORT=8080 \
    PYTHONUNBUFFERED=1

HEALTHCHECK --interval=30s --timeout=5s --start-period=10s --retries=3 \
  CMD python -c "import urllib.request; urllib.request.urlopen('http://127.0.0.1:8080/api/v1/health')" || exit 1

ENTRYPOINT ["uvicorn", "aegisops.api.app:create_app", "--factory", "--host", "0.0.0.0", "--port", "8080"]
