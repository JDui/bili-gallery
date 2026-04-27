#!/usr/bin/env bash
set -euo pipefail

ROOT_DIR="$(cd "$(dirname "$0")/.." && pwd)"
IMAGE_TAG="${1:-zzs-bili-gallery:amd64}"
REVIEW_PLATFORM="${REVIEW_PLATFORM:-}"
RUN_ID="$(date +"%Y%m%d_%H%M%S")"
REVIEW_DIR="$ROOT_DIR/review/$RUN_ID"
RUNTIME_DIR="$REVIEW_DIR/runtime_storage"
SCREEN_DIR="$REVIEW_DIR/screens"
CONTAINER_NAME="zzs-bili-gallery-review"
PORT="${REVIEW_PORT:-17860}"
BASE_URL="http://127.0.0.1:${PORT}"

mkdir -p "$SCREEN_DIR"

CHROME_TESTING_BIN="$(find "$HOME/Library/Caches/ms-playwright" -path '*Google Chrome for Testing.app/Contents/MacOS/Google Chrome for Testing' 2>/dev/null | sort | tail -n 1 || true)"

if ! command -v limactl >/dev/null 2>&1; then
    echo "缺少 limactl，无法控制本机 Docker 虚拟机" >&2
    exit 1
fi

if ! docker context ls >/dev/null 2>&1; then
    echo "Docker 客户端不可用" >&2
    exit 1
fi

if ! limactl list docker 2>/dev/null | grep -q "Running"; then
    limactl start docker >/dev/null
fi

if ! "$ROOT_DIR/.venv/bin/python" -c "import playwright" >/dev/null 2>&1; then
    "$ROOT_DIR/.venv/bin/pip" install playwright --trusted-host pypi.org --trusted-host files.pythonhosted.org
fi

if [[ -z "$CHROME_TESTING_BIN" ]]; then
    if ! "$ROOT_DIR/.venv/bin/python" -m playwright install chromium >/dev/null 2>&1; then
        "$ROOT_DIR/.venv/bin/python" -m playwright install chromium
    fi
fi

"$ROOT_DIR/.venv/bin/python" "$ROOT_DIR/scripts/seed_review_data.py" --storage-root "$RUNTIME_DIR"

cleanup() {
    docker --context=lima-docker rm -f "$CONTAINER_NAME" >/dev/null 2>&1 || true
}
trap cleanup EXIT

docker --context=lima-docker rm -f "$CONTAINER_NAME" >/dev/null 2>&1 || true
if [[ -n "$REVIEW_PLATFORM" ]]; then
    docker --context=lima-docker run -d --rm \
        --platform "$REVIEW_PLATFORM" \
        --name "$CONTAINER_NAME" \
        -e APP_STORAGE_ROOT=/tmp/review_storage \
        -v "$RUNTIME_DIR:/review_seed:ro" \
        -p "${PORT}:7860" \
        "$IMAGE_TAG" \
        sh -lc 'rm -rf /tmp/review_storage && mkdir -p /tmp/review_storage && cp -R /review_seed/. /tmp/review_storage && exec uvicorn app.main:app --host 0.0.0.0 --port 7860' >/dev/null
else
    docker --context=lima-docker run -d --rm \
        --name "$CONTAINER_NAME" \
        -e APP_STORAGE_ROOT=/tmp/review_storage \
        -v "$RUNTIME_DIR:/review_seed:ro" \
        -p "${PORT}:7860" \
        "$IMAGE_TAG" \
        sh -lc 'rm -rf /tmp/review_storage && mkdir -p /tmp/review_storage && cp -R /review_seed/. /tmp/review_storage && exec uvicorn app.main:app --host 0.0.0.0 --port 7860' >/dev/null
fi

for _ in $(seq 1 30); do
    if curl -fsS "$BASE_URL/api/health" >/dev/null 2>&1; then
        break
    fi
    sleep 1
done

curl -fsS "$BASE_URL/api/health" >/dev/null

"$ROOT_DIR/.venv/bin/python" "$ROOT_DIR/scripts/capture_review_screens.py" \
    --base-url "$BASE_URL" \
    --output-dir "$SCREEN_DIR"

echo "审查截图已输出到: $SCREEN_DIR"
