FROM --platform=$BUILDPLATFORM rust:1.83-slim AS rust-build

WORKDIR /opt/zzs

ARG TARGETPLATFORM
ENV RUSTUP_DIST_SERVER=https://mirrors.tuna.tsinghua.edu.cn/rustup \
    RUSTUP_UPDATE_ROOT=https://mirrors.tuna.tsinghua.edu.cn/rustup/rustup

COPY docker_app/rust ./docker_app/rust
RUN mkdir -p /usr/local/cargo \
    && printf '[source.crates-io]\nreplace-with = "tuna"\n[source.tuna]\nregistry = "sparse+https://mirrors.tuna.tsinghua.edu.cn/crates.io-index/"\n' > /usr/local/cargo/config.toml \
    && if [ "$TARGETPLATFORM" = "linux/amd64" ]; then \
        rustup target add x86_64-unknown-linux-musl \
        && cargo build --release --target x86_64-unknown-linux-musl --manifest-path docker_app/rust/Cargo.toml \
        && mkdir -p docker_app/rust/target/release-dist \
        && cp docker_app/rust/target/x86_64-unknown-linux-musl/release/media-worker docker_app/rust/target/release-dist/media-worker \
        && cp docker_app/rust/target/x86_64-unknown-linux-musl/release/indexer docker_app/rust/target/release-dist/indexer; \
    else \
        cargo build --release --manifest-path docker_app/rust/Cargo.toml \
        && mkdir -p docker_app/rust/target/release-dist \
        && cp docker_app/rust/target/release/media-worker docker_app/rust/target/release-dist/media-worker \
        && cp docker_app/rust/target/release/indexer docker_app/rust/target/release-dist/indexer; \
    fi

FROM python:3.12-slim

ENV PYTHONDONTWRITEBYTECODE=1 \
    PYTHONUNBUFFERED=1 \
    PIP_INDEX_URL=https://pypi.tuna.tsinghua.edu.cn/simple \
    PIP_TRUSTED_HOST=pypi.tuna.tsinghua.edu.cn \
    PYTHONPATH=/opt/zzs/docker_app:/workspace:/workspace/LivePhoto \
    APP_REPO_ROOT=/workspace \
    APP_STORAGE_ROOT=/storage \
    APP_MEDIA_WORKER_BIN=/opt/zzs/bin/media-worker \
    APP_INDEXER_BIN=/opt/zzs/bin/indexer \
    APP_THUMBNAIL_WORKERS=1

WORKDIR /opt/zzs/docker_app

COPY docker_app/requirements.txt /tmp/requirements.txt
RUN pip install --no-cache-dir -r /tmp/requirements.txt

RUN mkdir -p /storage/config /storage/data /workspace /workspace/LivePhoto

COPY docker_app /opt/zzs/docker_app
RUN mkdir -p /opt/zzs/bin \
    && printf '#!/bin/sh\nexec python -m app.sidecars.media_worker "$@"\n' > /opt/zzs/bin/media-worker \
    && printf '#!/bin/sh\nexec python -m app.sidecars.indexer "$@"\n' > /opt/zzs/bin/indexer \
    && chmod +x /opt/zzs/bin/media-worker /opt/zzs/bin/indexer
COPY bili_9pics_downloader.py /workspace/bili_9pics_downloader.py
COPY LivePhoto /workspace/LivePhoto

EXPOSE 7860

CMD ["uvicorn", "app.main:app", "--host", "0.0.0.0", "--port", "7860"]
