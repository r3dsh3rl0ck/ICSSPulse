# Stage 1: Builder
FROM python:3.11-slim as builder

WORKDIR /build

RUN apt-get update && apt-get install -y --no-install-recommends \
    gcc \
    build-essential \
    && rm -rf /var/lib/apt/lists/*

COPY requirements.txt .
RUN pip install --user --no-cache-dir -r requirements.txt

# Stage 2: Runtime
FROM python:3.11-slim

LABEL maintainer="r3dsh3rl0ck"
LABEL description="ICSSPulse Light: Protocol Controllers"

WORKDIR /app

RUN apt-get update && apt-get install -y --no-install-recommends \
    curl \
    && rm -rf /var/lib/apt/lists/*

COPY --from=builder /root/.local /root/.local

ENV PATH=/root/.local/bin:$PATH
ENV PYTHONUNBUFFERED=1
ENV PYTHONDONTWRITEBYTECODE=1

COPY app.py .
COPY modbus_handler.py .
COPY opcua_handler.py .
COPY s7comm_handler.py .
COPY mqtt_handler.py .
COPY f.env .
COPY docker-entrypoint.sh .
COPY templates/ ./templates/
COPY static/ ./static/
COPY opcua_certs/ ./opcua_certs/

RUN chmod +x docker-entrypoint.sh && \
    mkdir -p /app/opcua_certs && \
    chmod 755 /app/opcua_certs

EXPOSE 4444

HEALTHCHECK --interval=30s --timeout=10s --start-period=5s --retries=3 \
    CMD curl -f http://localhost:4444/ || exit 1

ENTRYPOINT ["/app/docker-entrypoint.sh"]
CMD ["python", "app.py"]