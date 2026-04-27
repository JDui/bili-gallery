#!/usr/bin/env bash
set -euo pipefail

export HOMEBREW_NO_AUTO_UPDATE=1
export HOMEBREW_NO_ENV_HINTS=1
export HOMEBREW_BREW_GIT_REMOTE="${HOMEBREW_BREW_GIT_REMOTE:-https://mirrors.tuna.tsinghua.edu.cn/git/homebrew/brew.git}"
export HOMEBREW_CORE_GIT_REMOTE="${HOMEBREW_CORE_GIT_REMOTE:-https://mirrors.tuna.tsinghua.edu.cn/git/homebrew/homebrew-core.git}"

if [[ "$(uname -s)" != "Darwin" ]]; then
  echo "该脚本仅支持 macOS。"
  exit 1
fi

if ! command -v brew >/dev/null 2>&1; then
  echo "未检测到 Homebrew，请先安装 Homebrew。"
  exit 1
fi

ensure_formula() {
  local name="$1"
  if brew list --formula "$name" >/dev/null 2>&1; then
    echo "[OK] $name 已安装"
  else
    echo "[INSTALL] 安装 $name"
    brew install "$name"
  fi
}

ensure_cask() {
  local name="$1"
  if brew list --cask "$name" >/dev/null 2>&1; then
    echo "[OK] $name 已安装"
  else
    echo "[INSTALL] 安装 $name"
    brew install --cask "$name"
  fi
}

wait_for_docker() {
  echo "[WAIT] 等待 Docker daemon 就绪"
  for _ in {1..90}; do
    if docker info >/dev/null 2>&1; then
      echo "[OK] Docker 已就绪"
      return 0
    fi
    sleep 2
  done
  return 1
}

ensure_formula python
ensure_formula docker-compose
ensure_formula docker
ensure_formula docker-buildx
ensure_formula colima

if open -Ra Docker; then
  echo "[START] 启动 Docker Desktop"
  open -a Docker
  if ! wait_for_docker; then
    echo "[WARN] Docker Desktop 未就绪，切换到 Colima"
  fi
fi

if ! docker info >/dev/null 2>&1; then
  echo "[START] 启动 Colima"
  colima start --runtime docker --cpu 4 --memory 6 --disk 60
  if ! wait_for_docker; then
    echo "Docker 运行时尚未完成启动，请稍后重新运行该脚本。"
    exit 1
  fi
fi

SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
REPO_ROOT="$(cd "$SCRIPT_DIR/../.." && pwd)"

mkdir -p "$REPO_ROOT/storage/config" "$REPO_ROOT/storage/data"

echo "[DONE] 依赖检查完成。"
echo "后续可在仓库根目录运行："
echo "  docker compose -f docker_app/docker-compose.example.yml up --build"
