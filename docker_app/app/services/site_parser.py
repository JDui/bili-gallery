from __future__ import annotations

from dataclasses import dataclass, field
from html.parser import HTMLParser
from pathlib import Path
from typing import Any
from urllib.parse import urljoin, urlparse
from xml.etree import ElementTree

import requests

from app.services.utils import parse_date, safe_slug

try:
    from bs4 import BeautifulSoup
except ImportError:  # pragma: no cover - fallback is covered through parser behavior
    BeautifulSoup = None


@dataclass
class ParsedAsset:
    url: str
    media_type: str


@dataclass
class ParsedPost:
    url: str
    title: str
    pub_date: str | None
    tags: list[str] = field(default_factory=list)
    excerpt: str = ""
    assets: list[ParsedAsset] = field(default_factory=list)


DEFAULT_SITE_USER_AGENT = (
    "Mozilla/5.0 (Windows NT 10.0; Win64; x64) "
    "AppleWebKit/537.36 (KHTML, like Gecko) "
    "Chrome/146.0.0.0 Safari/537.36"
)


def browser_like_site_headers(user_agent: str | None = None) -> dict[str, str]:
    return {
        "User-Agent": user_agent or DEFAULT_SITE_USER_AGENT,
        "Accept": "text/html,application/xhtml+xml,application/xml;q=0.9,image/avif,image/webp,*/*;q=0.8",
        "Accept-Language": "ja-JP,ja;q=0.9,en-US;q=0.8,en;q=0.7,zh-CN;q=0.6",
        "Connection": "close",
        "Upgrade-Insecure-Requests": "1",
    }


def site_request_timeout(read_timeout: int | float) -> tuple[float, float]:
    read_seconds = max(float(read_timeout or 300), 30.0)
    connect_seconds = min(20.0, max(10.0, read_seconds / 6))
    return (connect_seconds, read_seconds)


class PageFetcher:
    def __init__(
        self,
        timeout: int = 300,
        user_agent: str = DEFAULT_SITE_USER_AGENT,
        proxies: dict[str, str] | None = None,
    ) -> None:
        self.timeout = site_request_timeout(timeout)
        self.session = requests.Session()
        self.session.headers.update(browser_like_site_headers(user_agent))
        if proxies:
            self.session.proxies.update(proxies)

    def get_text(self, url: str) -> str:
        if url.startswith("file://"):
            return Path(urlparse(url).path).read_text(encoding="utf-8")
        response = self.session.get(url, timeout=self.timeout)
        response.raise_for_status()
        response.encoding = response.encoding or response.apparent_encoding
        return response.text


class HtmlNode:
    def __init__(self, name: str, attrs: dict[str, str] | None = None) -> None:
        self.name = name
        self.attrs = attrs or {}
        self.children: list[HtmlNode] = []
        self.text_parts: list[str] = []

    def get(self, key: str, default: str | None = None) -> str | None:
        return self.attrs.get(key, default)

    def get_text(self, separator: str = " ", strip: bool = True) -> str:
        parts = list(self.text_parts)
        for child in self.children:
            parts.append(child.get_text(separator=separator, strip=strip))
        text = separator.join(part for part in parts if part)
        return " ".join(text.split()) if strip else text

    def select_one(self, selector: str) -> "HtmlNode | None":
        items = self.select(selector)
        return items[0] if items else None

    def select(self, selector: str) -> list["HtmlNode"]:
        results: list[HtmlNode] = []
        seen: set[int] = set()
        for group in [item.strip() for item in selector.split(",") if item.strip()]:
            matched = self._select_group(group)
            for node in matched:
                if id(node) not in seen:
                    seen.add(id(node))
                    results.append(node)
        return results

    def _select_group(self, selector: str) -> list["HtmlNode"]:
        current = [self]
        for part in selector.split():
            next_nodes: list[HtmlNode] = []
            for node in current:
                next_nodes.extend([item for item in node._descendants() if _matches_selector(item, part)])
            current = next_nodes
        return current

    def _descendants(self) -> list["HtmlNode"]:
        output: list[HtmlNode] = []
        for child in self.children:
            output.append(child)
            output.extend(child._descendants())
        return output


class SimpleHtmlParser(HTMLParser):
    VOID_TAGS = {"area", "base", "br", "col", "embed", "hr", "img", "input", "link", "meta", "param", "source", "track", "wbr"}

    def __init__(self) -> None:
        super().__init__(convert_charrefs=True)
        self.root = HtmlNode("document")
        self.stack = [self.root]

    def handle_starttag(self, tag: str, attrs: list[tuple[str, str | None]]) -> None:
        node = HtmlNode(tag.lower(), {key.lower(): value or "" for key, value in attrs})
        self.stack[-1].children.append(node)
        if tag.lower() not in self.VOID_TAGS:
            self.stack.append(node)

    def handle_endtag(self, tag: str) -> None:
        tag = tag.lower()
        while len(self.stack) > 1:
            node = self.stack.pop()
            if node.name == tag:
                break

    def handle_data(self, data: str) -> None:
        if data.strip():
            self.stack[-1].text_parts.append(data.strip())


def parse_html(text: str) -> Any:
    if BeautifulSoup is not None:
        return BeautifulSoup(text, "lxml")
    parser = SimpleHtmlParser()
    parser.feed(text)
    return parser.root


def _matches_selector(node: HtmlNode, selector: str) -> bool:
    attr_name = attr_suffix = None
    if "[" in selector and selector.endswith("]"):
        selector, attr_part = selector.split("[", 1)
        attr_part = attr_part[:-1]
        if "$=" in attr_part:
            attr_name, attr_suffix = attr_part.split("$=", 1)
            attr_suffix = attr_suffix.strip("'\"")
        else:
            attr_name = attr_part.strip().lower()
    tag = ""
    class_name = ""
    element_id = ""
    if "#" in selector:
        selector, element_id = selector.split("#", 1)
    if "." in selector:
        tag, class_name = selector.split(".", 1)
    elif selector:
        tag = selector
    if tag and node.name != tag.lower():
        return False
    if class_name:
        classes = (node.get("class") or "").split()
        required_classes = [item for item in class_name.split(".") if item]
        if any(item not in classes for item in required_classes):
            return False
    if element_id and node.get("id") != element_id:
        return False
    if attr_name and attr_suffix is None:
        return node.get(attr_name.lower()) is not None
    if attr_name and attr_suffix is not None:
        value = node.get(attr_name.lower()) or ""
        if not value.lower().endswith(attr_suffix.lower()):
            return False
    return True


class SourceParser:
    def __init__(self, fetcher: PageFetcher) -> None:
        self.fetcher = fetcher

    def preview(self, source: dict[str, Any], limit: int = 3) -> list[ParsedPost]:
        return self.discover(source, limit=limit, parse_assets=False)

    def discover(self, source: dict[str, Any], limit: int | None = None, parse_assets: bool = True) -> list[ParsedPost]:
        source_type = str(source.get("source_type") or "html").lower()
        if source_type == "rss":
            posts = self._discover_rss(source, parse_assets=parse_assets, limit=limit)
        elif source_type == "sitemap":
            posts = self._discover_sitemap(source, parse_assets=parse_assets, limit=limit)
        else:
            posts = self._discover_html(source, parse_assets=parse_assets, limit=limit)
        return posts

    def _discover_html(self, source: dict[str, Any], parse_assets: bool, limit: int | None = None) -> list[ParsedPost]:
        posts: list[ParsedPost] = []
        seen: set[str] = set()
        max_pages = max(int(source.get("max_pages") or 1), 1)
        for page in range(1, max_pages + 1):
            page_url = self._page_url(source, page)
            soup = parse_html(self.fetcher.get_text(page_url))
            item_selector = source.get("list_item_selector")
            items = soup.select(item_selector) if item_selector else []
            if items:
                for item in items:
                    detail_url = self._detail_url(item, page_url, source)
                    if not detail_url:
                        continue
                    normalized_url = detail_url.split("#", 1)[0]
                    if normalized_url in seen:
                        continue
                    seen.add(normalized_url)
                    posts.append(self.parse_detail(normalized_url, source, parse_assets=parse_assets, fallback_node=item))
                    if limit and len(posts) >= limit:
                        return posts
                continue

            for detail_url in self._sniff_detail_urls(soup, page_url):
                normalized_url = detail_url.split("#", 1)[0]
                if normalized_url in seen:
                    continue
                seen.add(normalized_url)
                posts.append(self.parse_detail(normalized_url, source, parse_assets=parse_assets))
                if limit and len(posts) >= limit:
                    return posts
        return posts

    def _discover_rss(self, source: dict[str, Any], parse_assets: bool, limit: int | None = None) -> list[ParsedPost]:
        root = ElementTree.fromstring(self.fetcher.get_text(source["entry_url"]).encode("utf-8"))
        items = [node for node in root.iter() if self._xml_name(node.tag) in {"item", "entry"}]
        posts: list[ParsedPost] = []
        for item in items:
            title = self._xml_child_text(item, "title") or "未命名贴文"
            link = self._rss_link(item)
            if not link:
                continue
            pub_date = self._first_date(
                self._xml_child_text(item, "pubDate"),
                self._xml_child_text(item, "published"),
                self._xml_child_text(item, "updated"),
            )
            tags = [node.text.strip() for node in item.iter() if self._xml_name(node.tag) == "category" and node.text]
            excerpt = self._xml_child_text(item, "description") or self._xml_child_text(item, "summary") or ""
            assets = self._rss_assets(item, link)
            if parse_assets and source.get("media_selector"):
                detail = self.parse_detail(link, source, parse_assets=True)
                assets.extend(detail.assets)
                title = detail.title or title
                pub_date = detail.pub_date or pub_date
                tags = detail.tags or tags
                excerpt = detail.excerpt or excerpt
            posts.append(ParsedPost(link, title, pub_date, [tag for tag in tags if tag], excerpt, self._dedupe_assets(assets)))
            if limit and len(posts) >= limit:
                return self._dedupe_posts(posts)
        return self._dedupe_posts(posts)

    def _discover_sitemap(self, source: dict[str, Any], parse_assets: bool, limit: int | None = None) -> list[ParsedPost]:
        root = ElementTree.fromstring(self.fetcher.get_text(source["entry_url"]).encode("utf-8"))
        posts: list[ParsedPost] = []
        for item in [node for node in root.iter() if self._xml_name(node.tag) == "url"]:
            loc = self._xml_child_text(item, "loc")
            if not loc:
                continue
            lastmod = self._first_date(self._xml_child_text(item, "lastmod"))
            detail = self.parse_detail(loc, source, parse_assets=parse_assets)
            if not detail.pub_date:
                detail.pub_date = lastmod
            posts.append(detail)
            if limit and len(posts) >= limit:
                return self._dedupe_posts(posts)
        return self._dedupe_posts(posts)

    def parse_detail(self, url: str, source: dict[str, Any], parse_assets: bool = True, fallback_node: Any | None = None) -> ParsedPost:
        soup = parse_html(self.fetcher.get_text(url))
        title = self._selector_text(soup, source.get("title_selector"))
        if not title and fallback_node:
            title = self._selector_text(fallback_node, source.get("title_selector"))
        if not title:
            title = self._selector_text(soup, "h1") or self._selector_text(soup, "title") or "未命名贴文"
        pub_date = self._selector_date(soup, source.get("date_selector"))
        if not pub_date and fallback_node:
            pub_date = self._selector_date(fallback_node, source.get("date_selector"))
        tags = self._selector_texts(soup, source.get("tag_selector"))
        if not tags and fallback_node:
            tags = self._selector_texts(fallback_node, source.get("tag_selector"))
        excerpt = self._selector_text(soup, source.get("body_selector")) or ""
        assets = self._media_assets(soup, source.get("media_selector"), url) if parse_assets else []
        return ParsedPost(url=url, title=title.strip(), pub_date=pub_date, tags=tags, excerpt=excerpt.strip(), assets=assets)

    def _page_url(self, source: dict[str, Any], page: int) -> str:
        template = source.get("page_url_template")
        if template:
            return str(template).format(page=page)
        return source["entry_url"]

    def _detail_url(self, item: Any, base_url: str, source: dict[str, Any]) -> str | None:
        selector = source.get("detail_link_selector") or "a"
        link = item.select_one(selector)
        if not link:
            return None
        href = link.get("href") or link.get("src")
        if not href:
            nested = link.select_one("a[href]") if hasattr(link, "select_one") else None
            href = nested.get("href") if nested else None
        return urljoin(base_url, href) if href else None

    def _sniff_detail_urls(self, soup: Any, base_url: str) -> list[str]:
        candidates: list[tuple[int, str]] = []
        for link in soup.select("a[href]"):
            href = link.get("href")
            if not href:
                continue
            absolute = urljoin(base_url, href)
            score = self._detail_url_score(base_url, absolute, link.get_text(" ", strip=True))
            if score <= 0:
                continue
            candidates.append((score, absolute.split("#", 1)[0]))
        candidates.sort(key=lambda item: (-item[0], item[1]))
        output: list[str] = []
        seen: set[str] = set()
        for _score, url in candidates:
            if url in seen:
                continue
            seen.add(url)
            output.append(url)
        return output

    def _detail_url_score(self, base_url: str, candidate_url: str, link_text: str) -> int:
        parsed_base = urlparse(base_url)
        parsed_candidate = urlparse(candidate_url)
        if parsed_candidate.scheme not in {"http", "https", "file"}:
            return 0
        if parsed_base.scheme in {"http", "https"} and parsed_base.netloc != parsed_candidate.netloc:
            return 0
        if parsed_candidate.path == parsed_base.path and not parsed_candidate.query:
            return 0
        suffix = Path(parsed_candidate.path.lower()).suffix
        if suffix in {".jpg", ".jpeg", ".png", ".webp", ".gif", ".mp4", ".webm", ".mov", ".zip", ".rar", ".7z", ".pdf"}:
            return 0

        path = parsed_candidate.path.lower()
        text = (link_text or "").strip()
        score = 1
        if text:
            score += 1
        if any(token in path for token in ("/post", "/posts", "/article", "/entry", "/archives", "/blog", "/news")):
            score += 4
        if any(token in path for token in ("/20", "date=", "p=", "id=")):
            score += 2
        if len([part for part in path.split("/") if part]) >= 2:
            score += 1
        if any(token in path for token in ("/tag", "/category", "/author", "/page", "/login", "/contact", "/about", "/privacy")):
            score -= 3
        return max(score, 0)

    def _selector_text(self, soup: Any | None, selector: str | None) -> str:
        if not soup or not selector:
            return ""
        node = soup.select_one(selector)
        if not node:
            return ""
        return node.get("content") or node.get("datetime") or node.get_text(" ", strip=True)

    def _selector_texts(self, soup: Any | None, selector: str | None) -> list[str]:
        if not soup or not selector:
            return []
        return [node.get_text(" ", strip=True) for node in soup.select(selector) if node.get_text(" ", strip=True)]

    def _selector_date(self, soup: Any | None, selector: str | None) -> str | None:
        text = self._selector_text(soup, selector)
        parsed = parse_date(text)
        return parsed.isoformat() if parsed else None

    def _media_assets(self, soup: Any, selector: str | None, base_url: str) -> list[ParsedAsset]:
        if not selector:
            selector = "img, video, source, a[href$='.jpg'], a[href$='.jpeg'], a[href$='.png'], a[href$='.webp'], a[href$='.gif'], a[href$='.mp4'], a[href$='.webm'], a[href$='.mov']"
        assets: list[ParsedAsset] = []
        selected_nodes = soup.select(selector)
        if hasattr(soup, "find_all"):
            selected_ids = {id(node) for node in selected_nodes}
            selected_nodes = [node for node in soup.find_all(True) if id(node) in selected_ids]
        elif hasattr(soup, "_descendants"):
            selected_ids = {id(node) for node in selected_nodes}
            selected_nodes = [node for node in soup._descendants() if id(node) in selected_ids]
        for node in selected_nodes:
            url = node.get("src") or node.get("data-src") or node.get("data-original") or node.get("href")
            if not url:
                continue
            media_url = urljoin(base_url, url)
            media_type = "video" if node.name in {"video", "source"} or self._is_video_url(media_url) else "image"
            if media_type in {"image", "video"}:
                assets.append(ParsedAsset(media_url, media_type))
        return self._dedupe_assets(assets)

    def _rss_link(self, item: Any) -> str:
        for child in item.iter():
            if self._xml_name(child.tag) == "link":
                return child.attrib.get("href") or (child.text or "").strip()
        return ""

    def _rss_assets(self, item: Any, base_url: str) -> list[ParsedAsset]:
        assets: list[ParsedAsset] = []
        for node in item.iter():
            if self._xml_name(node.tag) not in {"enclosure", "content"}:
                continue
            url = node.attrib.get("url") or node.attrib.get("src")
            if not url:
                continue
            media_type_hint = (node.attrib.get("type") or "").lower()
            media_url = urljoin(base_url, url)
            media_type = "video" if "video" in media_type_hint or self._is_video_url(media_url) else "image"
            assets.append(ParsedAsset(media_url, media_type))
        return self._dedupe_assets(assets)

    def _first_date(self, *values: str | None) -> str | None:
        for value in values:
            parsed = parse_date(value)
            if parsed:
                return parsed.isoformat()
        return None

    def _xml_child_text(self, item: Any, name: str) -> str:
        for child in item.iter():
            if self._xml_name(child.tag) == name and child.text:
                return child.text.strip()
        return ""

    def _xml_name(self, tag: str) -> str:
        return tag.rsplit("}", 1)[-1].split(":")[-1]

    def _dedupe_posts(self, posts: list[ParsedPost]) -> list[ParsedPost]:
        output: list[ParsedPost] = []
        seen = set()
        for post in posts:
            if post.url in seen:
                continue
            seen.add(post.url)
            output.append(post)
        return output

    def _dedupe_assets(self, assets: list[ParsedAsset]) -> list[ParsedAsset]:
        output: list[ParsedAsset] = []
        seen = set()
        for asset in assets:
            key = asset.url.split("#", 1)[0]
            if key in seen:
                continue
            seen.add(key)
            output.append(asset)
        return output

    def _is_video_url(self, url: str) -> bool:
        return Path(urlparse(url).path.lower()).suffix in {".mp4", ".webm", ".mov", ".m4v"}
