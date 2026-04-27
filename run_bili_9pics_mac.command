#!/bin/zsh
set -e

SCRIPT_DIR="$(cd "$(dirname "$0")" && pwd)"
cd "$SCRIPT_DIR"

echo "Running bili_9pics_downloader.py ..."
python3 "$SCRIPT_DIR/bili_9pics_downloader.py"

echo
echo "Finished. Press Enter to close."
read
