# ZeroCloudGravity v1.0.1 — Hardened Non-Root Contextual MCP Container (Ubuntu 24.04)
FROM ubuntu:24.04

ENV DEBIAN_FRONTEND=noninteractive \
    PYTHONDONTWRITEBYTECODE=1 \
    PYTHONUNBUFFERED=1 \
    ZCG_NO_BROWSER=1 \
    LC_ALL=C.UTF-8 \
    LANG=C.UTF-8

RUN apt-get update \
    && apt-get install -y --no-install-recommends \
        ca-certificates \
        git \
        python3 \
        python3-pip \
        python3-venv \
    && rm -rf /var/lib/apt/lists/* \
    && groupadd --gid 10001 zcg \
    && useradd --uid 10001 --gid zcg --create-home --shell /usr/sbin/nologin zcg

WORKDIR /opt/zero-cloud-gravity

COPY VERSION LICENSE README.md pyproject.toml requirements.txt install.sh ./
COPY system ./system
COPY templates ./templates
COPY antigravity ./antigravity
COPY docs ./docs
COPY src ./src

RUN python3 -m venv /opt/zcg-venv \
    && /opt/zcg-venv/bin/pip install --no-cache-dir --upgrade pip \
    && /opt/zcg-venv/bin/pip install --no-cache-dir . \
    && chown -R zcg:zcg /opt/zero-cloud-gravity /opt/zcg-venv

ENV PATH="/opt/zcg-venv/bin:${PATH}" \
    ZCG_DIR="/opt/zero-cloud-gravity"

USER zcg

HEALTHCHECK --interval=30s --timeout=5s --start-period=5s --retries=3 \
    CMD ["zcg-mcp", "--self-test"]

ENTRYPOINT ["zcg-mcp"]
