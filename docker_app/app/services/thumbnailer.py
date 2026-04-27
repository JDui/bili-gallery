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
    def __init__(self, thumb_size: tuple[int, int] = (720, 720)) -> None:
        self.thumb_size = thumb_size

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

    def ensure_image_thumbnail(self, source: Path, target: Path) -> bool:
        if target.exists() and target.stat().st_mtime >= source.stat().st_mtime:
            return False
        ensure_parent(target)
        with Image.open(source) as image:
            normalized = ImageOps.exif_transpose(image).convert("RGB")
            normalized.thumbnail(self.thumb_size, Image.Resampling.LANCZOS)
            normalized.save(target, format="WEBP", quality=76, method=6)
        return True

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
