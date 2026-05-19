FROM node:22-bookworm-slim AS node-runtime

FROM python:3.11-slim

WORKDIR /workspace

ARG INSTALL_OPTIONAL=false
ARG INSTALL_MINERU_RUNTIME=true
ARG MINERU_VERSION=3.0.1
ARG MINERU_BUILD_MODEL_SOURCE=modelscope
ARG MINERU_BUILD_MODEL_TYPE=pipeline
ARG MINERU_BUILD_MODEL_TREE_SHA256=581698f99866ec54ce3997d0636743a430ecc119d35eda330058fdc0ab10a285

RUN sed -i 's|http://deb.debian.org/debian|https://mirrors.aliyun.com/debian|g; s|http://security.debian.org/debian-security|https://mirrors.aliyun.com/debian-security|g' /etc/apt/sources.list.d/debian.sources

RUN apt-get -o Acquire::Retries=5 -o Acquire::http::Timeout=30 update \
    && apt-get -o Acquire::Retries=5 -o Acquire::http::Timeout=30 install -y --no-install-recommends \
        bash \
        fontconfig \
        fonts-noto-core \
        libgl1 \
        libglib2.0-0 \
    && rm -rf /var/lib/apt/lists/*

COPY --from=node-runtime /usr/local/bin/node /usr/local/bin/node
COPY --from=node-runtime /usr/local/bin/npm /usr/local/bin/npm
COPY --from=node-runtime /usr/local/bin/npx /usr/local/bin/npx
COPY --from=node-runtime /usr/local/lib/node_modules/npm /usr/local/lib/node_modules/npm

ENV PIP_DEFAULT_TIMEOUT=120 \
    PIP_RETRIES=10 \
    PIP_INDEX_URL=https://mirrors.aliyun.com/pypi/simple \
    PIP_TRUSTED_HOST=mirrors.aliyun.com \
    EMATA_LARK_CLI_EXECUTABLE=npx

COPY backend/scripts/install-mineru-runtime.sh /tmp/install-mineru-runtime.sh
RUN chmod +x /tmp/install-mineru-runtime.sh \
    && if [ "$INSTALL_MINERU_RUNTIME" = "true" ]; then \
        MINERU_RUNTIME_ROOT=/opt/mineru-runtime \
        MINERU_VERSION="$MINERU_VERSION" \
        MINERU_BUILD_MODEL_SOURCE="$MINERU_BUILD_MODEL_SOURCE" \
        MINERU_BUILD_MODEL_TYPE="$MINERU_BUILD_MODEL_TYPE" \
        MINERU_BUILD_MODEL_TREE_SHA256="$MINERU_BUILD_MODEL_TREE_SHA256" \
        MINERU_TOOLS_CONFIG_JSON=/opt/mineru-runtime/config/mineru.json \
        HF_HOME=/opt/mineru-runtime/cache/huggingface \
        MODELSCOPE_CACHE=/opt/mineru-runtime/cache/modelscope \
        XDG_CACHE_HOME=/opt/mineru-runtime/cache \
        /tmp/install-mineru-runtime.sh \
        && ln -sf /opt/mineru-runtime/bin/mineru /usr/local/bin/mineru; \
      fi \
    && rm -f /tmp/install-mineru-runtime.sh

COPY backend/requirements.txt /workspace/backend/requirements.txt
RUN pip install --no-cache-dir -r /workspace/backend/requirements.txt
COPY backend/requirements-optional.txt /workspace/backend/requirements-optional.txt
RUN if [ "$INSTALL_OPTIONAL" = "true" ]; then pip install --no-cache-dir -r /workspace/backend/requirements-optional.txt; fi

COPY backend /workspace/backend

ENV PYTHONPATH=/workspace/backend

CMD ["uvicorn", "app.main:app", "--host", "0.0.0.0", "--port", "8000"]
