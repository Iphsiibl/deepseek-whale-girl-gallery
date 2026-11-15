#!/usr/bin/env python3
"""入库前的图片压缩 —— 加进画廊的图一律先压一遍再落盘。

为什么要有这一步
----------------

画廊页面要展示的是缩略图（``docs/thumbs/``，多档 WebP），但原图也会被
「原图链接」直接下载。一张 4K PNG 动辄 5~10 MB，几十张就能把仓库撑到
几百 MB，Pages 部署和访问都会变慢。

所以统一规矩：**入库的图先压成 WebP**。

* 长边超过 ``MAX_EDGE``（默认 2560）就等比缩到 2560 —— 展示用的最高档
  缩略图本来就只到 1920，再大的像素是纯浪费。
* 质量 ``QUALITY``（默认 82）：肉眼看不出差别，但体积通常能降到原来的
  1/5 ~ 1/20。
* 保留 alpha 通道（PNG 表情包常见的透明底不会变成黑底）。
* EXIF 方向先摆正，避免手机横竖拍的照片躺倒。

压缩完再走 ``make_thumbs.py`` 生成 480 / 960 / 1440 / 1920 四档展示图。
"""

from __future__ import annotations

import io
import shutil
from pathlib import Path

try:
    from PIL import Image, ImageOps
except ImportError:  # pragma: no cover
    raise SystemExit("缺少 Pillow，请先运行 pip install -r tools/requirements.txt")

#: 入库原图的长边上限（px）
MAX_EDGE = 2560
#: WebP 质量
QUALITY = 82
#: 支持读取的输入格式
INPUT_EXTS = {".png", ".jpg", ".jpeg", ".webp", ".gif", ".bmp", ".avif", ".tif", ".tiff"}


def compress_to_webp(src: Path, dst: Path, max_edge: int = MAX_EDGE, quality: int = QUALITY) -> dict:
    """把 ``src`` 压成 WebP 写到 ``dst``。

    返回 ``{"before", "after", "width", "height", "saved"}``（字节）。
    """
    before = src.stat().st_size
    with Image.open(src) as im:
        im = ImageOps.exif_transpose(im)
        if getattr(im, "is_animated", False):
            im.seek(0)
        has_alpha = im.mode in ("RGBA", "LA", "PA") or (im.mode == "P" and "transparency" in im.info)
        if im.mode not in ("RGB", "RGBA"):
            im = im.convert("RGBA" if has_alpha else "RGB")
        w, h = im.size
        scale = min(1.0, max_edge / float(max(w, h)))
        if scale < 1.0:
            im = im.resize((max(1, round(w * scale)), max(1, round(h * scale))), Image.LANCZOS)
        dst.parent.mkdir(parents=True, exist_ok=True)
        im.save(dst, "WEBP", quality=quality, method=6)
        size = im.size
    after = dst.stat().st_size
    return {
        "before": before,
        "after": after,
        "width": size[0],
        "height": size[1],
        "saved": max(0, before - after),
    }


def store_image(
    src: Path,
    group_dir: Path,
    image_id: str,
    compress: bool = True,
    max_edge: int = MAX_EDGE,
    quality: int = QUALITY,
) -> tuple[Path, dict]:
    """把 ``src`` 存进 ``group_dir``，返回 ``(落盘路径, 压缩信息)``。

    * ``compress=True``（默认）：压成 WebP，文件名 ``<id>.webp``。
    * ``compress=False``：原样拷贝，保留原扩展名（仅用于特殊场景）。
    """
    group_dir.mkdir(parents=True, exist_ok=True)
    if not compress:
        suffix = src.suffix.lower() or ".png"
        dst = group_dir / f"{image_id}{suffix}"
        shutil.copy2(src, dst)
        with Image.open(dst) as im:
            w, h = im.size
        return dst, {"before": src.stat().st_size, "after": dst.stat().st_size, "width": w, "height": h, "saved": 0}

    dst = group_dir / f"{image_id}.webp"
    info = compress_to_webp(src, dst, max_edge=max_edge, quality=quality)
    return dst, info


def read_bytes_preview(data: bytes) -> tuple[int, int] | None:
    """从内存里的图片字节读尺寸（给上传接口用）。"""
    try:
        with Image.open(io.BytesIO(data)) as im:
            return im.size
    except Exception:
        return None
