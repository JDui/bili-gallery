from __future__ import annotations

import argparse
from pathlib import Path

from playwright.sync_api import Page, expect, sync_playwright


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(description="抓取关键页面审查截图")
    parser.add_argument("--base-url", required=True, help="应用地址")
    parser.add_argument("--output-dir", required=True, help="截图输出目录")
    return parser.parse_args()


def save(page: Page, output_dir: Path, filename: str, full_page: bool = True) -> None:
    page.screenshot(path=str(output_dir / filename), full_page=full_page)


def find_chromium_executable() -> str | None:
    cache_root = Path.home() / "Library" / "Caches" / "ms-playwright"
    candidates = sorted(
        cache_root.glob("chromium-*/chrome-mac-arm64/Google Chrome for Testing.app/Contents/MacOS/Google Chrome for Testing"),
        reverse=True,
    )
    for candidate in candidates:
        if candidate.exists():
            return str(candidate)
    return None


def main() -> None:
    args = parse_args()
    output_dir = Path(args.output_dir).resolve()
    output_dir.mkdir(parents=True, exist_ok=True)

    with sync_playwright() as playwright:
        executable_path = find_chromium_executable()
        browser = playwright.chromium.launch(headless=True, executable_path=executable_path)
        page = browser.new_page(viewport={"width": 1512, "height": 1080}, device_scale_factor=1.5)
        page.goto(args.base_url, wait_until="networkidle")

        expect(page.locator("[data-testid='section-gallery']")).to_be_visible()
        page.locator(".gallery-toolbar .secondary-button").first.click()
        expect(page.locator(".time-filter-panel")).to_be_visible()
        save(page, output_dir, "gallery.png")
        page.locator(".gallery-toolbar .secondary-button").first.click()

        mobile = browser.new_page(viewport={"width": 430, "height": 932}, is_mobile=True, has_touch=True, device_scale_factor=2)
        try:
            mobile.goto(args.base_url, wait_until="networkidle")
            expect(mobile.locator("[data-testid='section-gallery']")).to_be_visible()
            mobile.locator(".topbar .icon-button").click(force=True)
            mobile.wait_for_timeout(350)
            if mobile.locator(".sidebar.open").count():
                expect(mobile.locator(".sidebar.open")).to_be_visible()
            save(mobile, output_dir, "gallery-mobile.png", full_page=False)
        finally:
            mobile.close()

        page.locator(".shell").evaluate(
            """
            async (el) => {
                await Alpine.$data(el).setGalleryViewMode('pair');
            }
            """
        )
        expect(page.locator(".asset-masonry")).to_be_attached(timeout=10000)
        expect(page.locator(".asset-masonry .asset-card").first).to_be_visible(timeout=10000)
        save(page, output_dir, "gallery-pair.png")
        page.locator(".shell").evaluate(
            """
            async (el) => {
                await Alpine.$data(el).setGalleryViewMode('folder');
            }
            """
        )
        expect(page.locator(".masonry .photo-card").first).to_be_visible(timeout=10000)

        page.get_by_test_id("photo-card").first.click()
        expect(page.locator("[data-testid='detail-backdrop']")).to_be_visible()
        page.get_by_test_id("detail-card").first.click()
        expect(page.locator("[data-testid='viewer-backdrop']")).to_be_visible()
        save(page, output_dir, "viewer.png", full_page=False)
        page.keyboard.press("Escape")
        page.keyboard.press("Escape")

        page.get_by_test_id("nav-review").click()
        expect(page.locator("[data-testid='section-review']")).to_be_visible()
        save(page, output_dir, "review.png")

        page.get_by_test_id("nav-logs").click()
        expect(page.locator("[data-testid='section-logs']")).to_be_visible()
        save(page, output_dir, "logs.png")

        page.get_by_test_id("nav-tasks").click()
        expect(page.locator("[data-testid='section-tasks']")).to_be_visible()
        save(page, output_dir, "tasks.png")

        page.get_by_test_id("nav-trash").click()
        expect(page.locator("[data-testid='section-trash']")).to_be_visible()
        save(page, output_dir, "trash.png")

        page.get_by_test_id("nav-settings").click()
        expect(page.locator("[data-testid='section-settings']")).to_be_visible()
        page.get_by_role("button", name="生成二维码").click()
        expect(page.locator(".qr-box img")).to_be_visible(timeout=10000)
        save(page, output_dir, "settings.png")

        page.get_by_test_id("nav-subscriptions").click()
        expect(page.locator("[data-testid='section-subscriptions']")).to_be_visible()
        save(page, output_dir, "subscriptions.png")

        browser.close()


if __name__ == "__main__":
    main()
