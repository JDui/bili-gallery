from __future__ import annotations

import shutil
import subprocess
from pathlib import Path

from PIL import Image, ImageOps

from app.services.utils import ensure_parent

try:
    from imageio_ffmpeg import get_ffmpeg_exe as bundled_ffmpeg_exe
except ImportError:  # pragma: no cover - optional runtime fallback
    bundled_ffmpeg_exe = None


class ThumbnailService:
    def __init__(
        self,
        thumb_size: tuple[int, int] = (576, 576),
        small_thumb_size: tuple[int, int] = (192, 192),
        tiny_thumb_size: tuple[int, int] = (32, 32),
    ) -> None:
        self.thumb_size = thumb_size
        self.small_thumb_size = small_thumb_size
        self.tiny_thumb_size = tiny_thumb_size

    def _resolve_ffmpeg(self) -> str | None:
        ffmpeg = shutil.which("ffmpeg")
        if ffmpeg:
            return ffmpeg
        if bundled_ffmpeg_exe is None:
            return None
        try:
            return bundled_ffmpeg_exe()
        except RuntimeError:
            return None

    def ensure_image_thumbnail(
        self,
        source: Path,
        target: Path,
        size: tuple[int, int] | None = None,
        quality: int = 68,
    ) -> bool:
        target_size = size or self.thumb_size
        if target.exists() and target.stat().st_mtime >= source.stat().st_mtime and self._thumbnail_matches(target, source, target_size):
            return False
        ensure_parent(target)
        with Image.open(source) as image:
            normalized = ImageOps.exif_transpose(image).convert("RGB")
            normalized = self._resize_to_short_edge(normalized, min(target_size))
            normalized.save(target, format="WEBP", quality=quality, method=6)
        return True

    def ensure_small_image_thumbnail(self, source: Path, target: Path) -> bool:
        return self.ensure_image_thumbnail(source, target, size=self.small_thumb_size, quality=48)

    def ensure_tiny_image_thumbnail(self, source: Path, target: Path) -> bool:
        try:
            return self.ensure_image_thumbnail(source, target, size=self.tiny_thumb_size, quality=28)
        except Exception:
            return False

    def _thumbnail_matches(self, target: Path, source: Path, size: tuple[int, int]) -> bool:
        try:
            with Image.open(target) as image:
                width, height = image.size
            with Image.open(source) as image:
                source_width, source_height = image.size
        except Exception:
            return False
        expected_short_edge = min(min(source_width, source_height), min(size))
        return min(width, height) == expected_short_edge

    def _resize_to_short_edge(self, image: Image.Image, short_edge: int) -> Image.Image:
        width, height = image.size
        current_short_edge = min(width, height)
        if current_short_edge <= 0 or current_short_edge <= short_edge:
            return image
        scale = short_edge / current_short_edge
        target_size = (max(1, round(width * scale)), max(1, round(height * scale)))
        return image.resize(target_size, Image.Resampling.LANCZOS)

    def ensure_video_cover(self, source: Path, cover_target: Path) -> bool:
        if cover_target.exists() and cover_target.stat().st_mtime >= source.stat().st_mtime:
            return False
        ensure_parent(cover_target)
        ffmpeg = self._resolve_ffmpeg()
        if not ffmpeg:
            return False
        command = [
            ffmpeg,
            "-y",
            "-i",
            str(source),
            "-vf",
            "thumbnail,scale=960:-1",
            "-frames:v",
            "1",
            str(cover_target),
        ]
        subprocess.run(command, check=False, capture_output=True)
        return cover_target.exists()

    def ensure_reverse_video(self, source: Path, reverse_target: Path) -> bool:
        if reverse_target.exists() and reverse_target.stat().st_mtime >= source.stat().st_mtime:
            return False
        ensure_parent(reverse_target)
        ffmpeg = self._resolve_ffmpeg()
        if not ffmpeg:
            return False
        command = [
            ffmpeg,
            "-y",
            "-i",
            str(source),
            "-vf",
            "reverse",
            "-af",
            "areverse",
            str(reverse_target),
        ]
        subprocess.run(command, check=False, capture_output=True)
        return reverse_target.exists()
