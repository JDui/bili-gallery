from __future__ import annotations

import sys
from pathlib import Path

REPO_ROOT = Path(__file__).resolve().parents[3]
if str(REPO_ROOT) not in sys.path:
    sys.path.insert(0, str(REPO_ROOT))

import bili_9pics_downloader as legacy_9pics  # noqa: E402

API_DETAIL = legacy_9pics.API_DETAIL
API_FEED = legacy_9pics.API_FEED
FEATURES = legacy_9pics.FEATURES
USER_AGENT = legacy_9pics.USER_AGENT
build_headers = legacy_9pics.build_headers
compact_text = legacy_9pics.compact_text
detail_params = legacy_9pics.detail_params
feed_params = legacy_9pics.feed_params
extract_picture_nodes = legacy_9pics.extract_picture_nodes
extract_primary_text = legacy_9pics.extract_primary_text
extract_pub_ts = legacy_9pics.extract_pub_ts
is_top_item = legacy_9pics.is_top_item
find_nine_pic_blocks = legacy_9pics.find_nine_pic_blocks
format_pub_time = legacy_9pics.format_pub_time
iter_space_pages = legacy_9pics.iter_space_pages
request_json = legacy_9pics.request_json
safe_filename = legacy_9pics.safe_filename
